"""Local Retriever — Layer B (#19).

자연어 질문 → entity 식별 (LLM 1단계) → 그래프 subgraph 추출 (Cypher, read-only)
→ 자연어 답변 (LLM 2단계).

W4 두 번째 retrieval. text2cypher.py (#18) 의 패턴을 그대로 재활용하되,
LLM 이 Cypher 를 직접 짜는 대신 *entity 만 식별*하고 subgraph 는 결정적
Cypher 템플릿으로 추출. "관계/연관" 질문에 강함.

흐름:
  자연어 질문
     ↓ _identify_entities (LLM 1단계, JSON 응답, kg/extractor.py 패턴)
  entity 후보 [{name, label?}, ...]
     ↓ _match_entities (Neo4j name/aliases CONTAINS — fulltext index 없을 때 대비)
  매칭된 Entity 노드들
     ↓ _expand_subgraph (1-hop Layer B 관계 + MENTIONS 청크)
  subgraph (entities, relationships, chunks)
     ↓ _format_context (토큰 절약 — top-N + truncate)
     ↓ _generate_answer (LLM 2단계, plain text)
  자연어 답변

text2cypher 와의 차이:
- text2cypher: LLM 이 Cypher 자유 생성 → factual / topN 질문에 강함.
- local_retriever: 결정적 entity 중심 traversal → 관계 / co-mention 질문에 강함.

#21 Routing Agent (5/18 작업) 에서 질문 키워드 기반으로 둘 중 하나로 분기.

안전장치:
1. **read-only 강제**: Cypher 템플릿이 결정적이라 사용자 입력이 Cypher 에 안 들어감 (parameterized).
2. **결과 크기 제한**: max_entities, max_hops, max_chunks_per_entity 로 토큰 폭발 방지.
3. **graceful fallback**: entity 0개 매칭 / LLM 실패 / 빈 subgraph 모두 자연어 안내.

#24 Opik:
- 공개 진입점 `local_retrieve` 에 `@track` — 질문/entity 수/subgraph 크기/소요 trace.

5/16 발견 자산 활용:
- Entity 라벨 품질 challenge (Company 라벨에 metric 혼재) → 답변 프롬프트가 결과 검토 후
  한 줄 정직하게 언급하도록 가이드.
- "두산밥캣" 같은 alias 매칭은 CONTAINS + aliases 배열 검색으로 강건하게.

Reference:
- retrieval/text2cypher.py — LLM 호출 / JSON 파싱 / 프롬프트 로드 / @track 패턴 그대로.
- kg/extractor.py — entity 추출 시 JSON 강제 + tenacity 재시도 패턴.
- Microsoft GraphRAG Local Search — entity 를 graph 진입점으로 활용하는 컨셉 차용.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.llm_client import LLMClient
from kg.neo4j_client import Neo4jClient
from observability.tracing import track

logger = logging.getLogger(__name__)


# ── 상수 (text2cypher 와 일치) ───────────────────────────────
TEMPERATURE_IDENTIFY = 0.1
TEMPERATURE_ANSWER = 0.3
MAX_TOKENS_IDENTIFY = 400
MAX_TOKENS_ANSWER = 700

# Subgraph 크기 제한 (토큰 폭발 방지)
MAX_ENTITIES_TO_EXPAND = 5      # 식별 entity 중 top N 만 expand
MAX_RELATED_PER_ENTITY = 15     # entity 당 이웃 노드 상한
MAX_CHUNKS_PER_ENTITY = 3       # entity 당 인용 청크 상한 (raw text)
CHUNK_TEXT_TRUNCATE = 300       # 청크 1개당 char 상한 (LLM 컨텍스트 절약)

# 프롬프트 경로
PROMPTS_DIR = Path(__file__).parent / "prompts"
ENTITY_PROMPT_PATH = PROMPTS_DIR / "local_retriever_entity_v1.md"
ANSWER_PROMPT_PATH = PROMPTS_DIR / "local_retriever_answer_v1.md"

# 지원 entity 라벨 (스키마 §3 — extractor 와 일치)
SUPPORTED_LABELS = ("Company", "Risk", "Metric", "Outlook", "Recommendation")


# ── 결과 객체 / 예외 ─────────────────────────────────────────
@dataclass
class LocalRetrieverResult:
    """Local Retriever 한 회차의 전체 trace.

    DoD (#19):
    - 관계 질의에서 VectorRAG 와 다른 답변 패턴 (subgraph 정보 활용)
    - 평균 응답 시간 < 5초

    Opik / Aura console 디버깅용 모든 중간 산물 보존.
    """

    question: str
    identified_entities: list[dict[str, Any]] = field(default_factory=list)  # LLM 식별
    matched_entities: list[dict[str, Any]] = field(default_factory=list)     # Neo4j 매칭
    subgraph_nodes: int = 0       # 이웃 노드 수 (중복 제거 후)
    subgraph_relations: int = 0   # 관계 edges 수
    subgraph_chunks: int = 0      # 인용된 청크 수
    answer: str = ""
    elapsed_seconds: float = 0.0
    error: str | None = None


class LocalRetrieverError(Exception):
    """Local Retriever 내부 오류. 호출자가 알아야 할 경우에만 raise.

    LLM 호출 실패 / entity 0개 매칭 같이 자연어로 안내 가능한 케이스는 raise 하지
    않고 `LocalRetrieverResult.error` 에 메시지를 박아서 graceful 반환.
    """


# ── 프롬프트 로드 ────────────────────────────────────────────
def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── JSON 파싱 (text2cypher 와 동일 패턴) ─────────────────────
_CODEFENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_codefence(raw: str) -> str:
    raw = raw.strip()
    m = _CODEFENCE_RE.match(raw)
    return m.group(1).strip() if m else raw


def _parse_identify_json(raw: str) -> dict[str, Any]:
    """LLM 1단계 (entity 식별) 응답 파싱.

    예상 형식:
      {"entities": [{"name": "두산밥캣", "label": "Company"}, ...],
       "explanation": "질문에서 ..."}
    """
    cleaned = _strip_codefence(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # extractor 와 동일 — 따옴표 escape 보정
        fixed = re.sub(r'(?<=: ")([^"]*)\'([^"]*?)(?=")', r"\1\'\2", cleaned)
        return json.loads(fixed)


# ── LLM 호출 (재시도) ────────────────────────────────────────
@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _call_llm_json(llm: LLMClient, system_prompt: str, user_prompt: str) -> str:
    return llm.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=TEMPERATURE_IDENTIFY,
        max_tokens=MAX_TOKENS_IDENTIFY,
        response_format={"type": "json_object"},
    )


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _call_llm_text(llm: LLMClient, system_prompt: str, user_prompt: str) -> str:
    return llm.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=TEMPERATURE_ANSWER,
        max_tokens=MAX_TOKENS_ANSWER,
    )


# ── 1단계: Entity 식별 ───────────────────────────────────────
def _identify_entities(
    llm: LLMClient, question: str, system_prompt: str
) -> tuple[list[dict[str, Any]], str]:
    """질문 → ([{name, label?}, ...], explanation).

    LLM 이 질문에서 검색 대상 entity 를 추출. 라벨은 hint 일 뿐 강제 아님
    (Kimi 의 라벨 부여 한계 — 5/16 challenge — 를 답변 단계가 정직하게 다룸).

    빈 리스트 / LLM 실패는 ([], error_msg) 로 graceful.
    """
    user_prompt = f"질문: {question}"
    try:
        raw = _call_llm_json(llm, system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("Entity 식별 LLM 호출 실패: %s", exc)
        return [], f"LLM 호출 실패: {exc}"

    try:
        data = _parse_identify_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Entity 식별 응답 JSON 파싱 실패: %s | raw=%r", exc, raw[:200])
        return [], f"JSON 파싱 실패: {exc}"

    entities = data.get("entities") or []
    explanation = (data.get("explanation") or "").strip()

    # 정규화 — name 필수, label 은 hint
    normalized: list[dict[str, Any]] = []
    for e in entities:
        if not isinstance(e, dict):
            continue
        name = (e.get("name") or "").strip()
        if not name:
            continue
        label = (e.get("label") or "").strip()
        if label and label not in SUPPORTED_LABELS:
            # 라벨 hint 가 스키마 외면 무시 (None 처리)
            label = ""
        normalized.append({"name": name, "label": label or None})

    return normalized, explanation


# ── 2단계: Neo4j 에서 entity 매칭 ────────────────────────────
_MATCH_ENTITIES_CYPHER = """
UNWIND $names AS qname
MATCH (e:Entity)
WHERE toLower(e.name) CONTAINS toLower(qname)
   OR ANY(a IN coalesce(e.aliases, []) WHERE toLower(a) CONTAINS toLower(qname))
WITH qname, e
ORDER BY size(e.name) ASC      // 짧은 이름 우선 (정확 매칭 가까운 쪽)
WITH qname, collect(e)[..3] AS top_matches  // entity 당 top 3 매칭
UNWIND top_matches AS e
RETURN qname,
       elementId(e) AS id,
       e.name AS name,
       labels(e) AS labels,
       e.aliases AS aliases,
       coalesce(e.member_count, 1) AS member_count
LIMIT 30
"""


def _match_entities(
    neo4j: Neo4jClient, identified: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """LLM 식별 entity name 들을 Neo4j 에서 실제 노드와 매칭.

    name / aliases CONTAINS 매칭 (대소문자 무관). fulltext index 가 있으면
    더 정확하지만 W3 단계에서 미적용이라 안전한 string 검색 사용.

    Returns:
        매칭된 노드 dict list. 각 dict: {qname, id, name, labels, aliases, member_count}
    """
    if not identified:
        return []
    names = [e["name"] for e in identified]
    try:
        rows = neo4j.read(_MATCH_ENTITIES_CYPHER, names=names)
    except Exception as exc:
        logger.warning("Entity 매칭 Cypher 실패: %s", exc)
        return []
    return rows


# ── 3단계: Subgraph 확장 (1-hop Layer B + MENTIONS) ─────────
_EXPAND_SUBGRAPH_CYPHER = """
UNWIND $ids AS eid
MATCH (e:Entity) WHERE elementId(e) = eid
// 1-hop Layer B 관계 이웃 (방향 무관)
OPTIONAL MATCH (e)-[r]-(neighbor:Entity)
WHERE type(r) IN ['FACES_RISK','HAS_METRIC','HAS_OUTLOOK','RECOMMENDED_FOR']
WITH e, collect(DISTINCT {
        rel: type(r),
        direction: CASE WHEN startNode(r) = e THEN 'out' ELSE 'in' END,
        neighbor_name: neighbor.name,
        neighbor_labels: labels(neighbor)
     })[..$max_related] AS relations
// 같은 청크에 등장한 다른 entity (co-mention)
OPTIONAL MATCH (e)<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(co:Entity)
WHERE co <> e
WITH e, relations, collect(DISTINCT {
        co_name: co.name,
        co_labels: labels(co)
     })[..$max_related] AS co_mentions
// entity 가 등장한 chunk 원문 (max_chunks 개만)
OPTIONAL MATCH (e)<-[:MENTIONS]-(c2:Chunk)
WITH e, relations, co_mentions, collect(DISTINCT {
        chunk_id: c2.id,
        text: substring(c2.text, 0, $chunk_truncate),
        page: c2.page
     })[..$max_chunks] AS chunks
RETURN e.name AS name,
       labels(e) AS labels,
       coalesce(e.member_count, 1) AS member_count,
       relations,
       co_mentions,
       chunks
"""


def _expand_subgraph(
    neo4j: Neo4jClient, matched_ids: list[str]
) -> list[dict[str, Any]]:
    """매칭 entity 들의 1-hop subgraph 추출.

    각 entity 별:
    - Layer B 관계 이웃 (FACES_RISK / HAS_METRIC / HAS_OUTLOOK / RECOMMENDED_FOR)
    - co-mention entity (같은 청크에 함께 등장)
    - entity 가 등장한 청크 원문 (top N, 토큰 절약 위해 truncate)

    토큰 폭발 방지를 위해 모든 collection 에 [..N] slice 적용.
    """
    if not matched_ids:
        return []
    # top N entity 만 expand (식별이 너무 많으면 token 폭발)
    ids_to_expand = matched_ids[:MAX_ENTITIES_TO_EXPAND]
    try:
        rows = neo4j.read(
            _EXPAND_SUBGRAPH_CYPHER,
            ids=ids_to_expand,
            max_related=MAX_RELATED_PER_ENTITY,
            max_chunks=MAX_CHUNKS_PER_ENTITY,
            chunk_truncate=CHUNK_TEXT_TRUNCATE,
        )
    except Exception as exc:
        logger.warning("Subgraph 확장 Cypher 실패: %s", exc)
        return []
    return rows


# ── 4단계: subgraph → LLM 컨텍스트 → 답변 ────────────────────
def _format_context(subgraph: list[dict[str, Any]]) -> dict[str, Any]:
    """LLM 답변 생성기에 전달할 컨텍스트 구조화.

    LLM 이 자연스럽게 읽을 수 있도록 entity 별로 묶고, 빈 필드는 생략.
    """
    formatted = []
    total_nodes = 0
    total_relations = 0
    total_chunks = 0
    for entry in subgraph:
        ent = {
            "name": entry["name"],
            "labels": entry["labels"],
            "member_count": entry["member_count"],
        }
        rels = [r for r in (entry.get("relations") or []) if r.get("neighbor_name")]
        cos = [c for c in (entry.get("co_mentions") or []) if c.get("co_name")]
        chunks = [c for c in (entry.get("chunks") or []) if c.get("chunk_id")]
        if rels:
            ent["layer_b_relations"] = rels
            total_relations += len(rels)
        if cos:
            ent["co_mentioned_entities"] = cos
            total_nodes += len(cos)
        if chunks:
            ent["sample_chunks"] = chunks
            total_chunks += len(chunks)
        formatted.append(ent)

    return {
        "entities": formatted,
        "stats": {
            "n_entities": len(formatted),
            "n_neighbors": total_nodes,
            "n_relations": total_relations,
            "n_chunks": total_chunks,
        },
    }


def _generate_answer(
    llm: LLMClient,
    question: str,
    identified: list[dict[str, Any]],
    matched: list[dict[str, Any]],
    context: dict[str, Any],
    answer_system_prompt: str,
    fallback_reason: str = "",
) -> str:
    """질문 + subgraph context → 자연어 답변.

    빈 subgraph / 매칭 0개 / LLM 실패 모두 LLM 에 그대로 넘겨서 자연스럽게 안내.
    """
    user_payload = {
        "question": question,
        "identified_entities": identified,
        "matched_entity_names": [m["name"] for m in matched],
        "subgraph": context,
        "fallback_reason": fallback_reason,
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)

    try:
        answer = _call_llm_text(llm, answer_system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("Answer 생성 LLM 호출 실패: %s", exc)
        # 최후 fallback
        if not matched:
            return (
                f"질문에서 추출한 entity ({[e['name'] for e in identified]}) 를 "
                f"그래프에서 찾지 못했습니다."
            )
        n = context.get("stats", {}).get("n_entities", 0)
        return f"매칭된 entity {n}개의 subgraph 를 찾았으나 자연어 변환에 실패했습니다."

    return answer.strip()


# ── 공개 인터페이스 ──────────────────────────────────────────
@track
def local_retrieve(
    question: str,
    llm: LLMClient | None = None,
    neo4j: Neo4jClient | None = None,
) -> LocalRetrieverResult:
    """자연어 질문 → entity 식별 → 1-hop subgraph → 자연어 답변.

    DoD (#19):
    - 관계 질의에서 VectorRAG 와 다른 답변 패턴 (subgraph 정보 활용) ✅
    - 평균 응답 시간 < 5초 (LLM 2회 호출이라 빠듯할 수 있음 — 측정)

    Args:
        question: 사용자 자연어 질문.
        llm: 테스트용 mock 주입 가능. 기본 LLMClient().
        neo4j: 테스트용 mock 주입 가능. 기본 Neo4jClient().

    Returns:
        LocalRetrieverResult — 전체 trace 포함. answer 는 항상 채워짐.
    """
    if not question or not question.strip():
        return LocalRetrieverResult(
            question=question,
            answer="질문이 비어 있습니다. 그래프에 대해 궁금한 점을 입력해 주세요.",
        )

    llm = llm or LLMClient()
    own_neo4j = neo4j is None
    neo4j = neo4j or Neo4jClient()

    entity_system_prompt = _load_prompt(ENTITY_PROMPT_PATH)
    answer_system_prompt = _load_prompt(ANSWER_PROMPT_PATH)

    started = time.perf_counter()
    logger.info("LocalRetriever 시작 — question=%r", question)

    try:
        # 1단계: Entity 식별
        identified, explanation = _identify_entities(
            llm, question, entity_system_prompt
        )

        if not identified:
            answer = _generate_answer(
                llm, question, [], [], {"entities": [], "stats": {}},
                answer_system_prompt,
                fallback_reason=explanation or "질문에서 검색 대상 entity 를 식별하지 못했습니다.",
            )
            elapsed = time.perf_counter() - started
            logger.info(
                "LocalRetriever 완료 (entity 식별 0개) elapsed=%.2fs", elapsed
            )
            return LocalRetrieverResult(
                question=question,
                identified_entities=[],
                answer=answer,
                elapsed_seconds=elapsed,
            )

        # 2단계: Neo4j 매칭
        matched = _match_entities(neo4j, identified)

        if not matched:
            answer = _generate_answer(
                llm, question, identified, [], {"entities": [], "stats": {}},
                answer_system_prompt,
                fallback_reason=(
                    f"질문에서 추출한 entity 후보 "
                    f"({[e['name'] for e in identified]}) 가 그래프에 적재되지 않았습니다."
                ),
            )
            elapsed = time.perf_counter() - started
            logger.info(
                "LocalRetriever 완료 (매칭 0개) elapsed=%.2fs", elapsed
            )
            return LocalRetrieverResult(
                question=question,
                identified_entities=identified,
                matched_entities=[],
                answer=answer,
                elapsed_seconds=elapsed,
            )

        # 3단계: Subgraph 확장
        matched_ids = list({m["id"] for m in matched})  # 중복 제거
        subgraph = _expand_subgraph(neo4j, matched_ids)

        # 4단계: 컨텍스트 포맷 + 답변 생성
        context = _format_context(subgraph)
        answer = _generate_answer(
            llm, question, identified, matched, context, answer_system_prompt,
        )

        elapsed = time.perf_counter() - started
        stats = context.get("stats", {})
        logger.info(
            "LocalRetriever 완료 — entities=%d neighbors=%d relations=%d "
            "chunks=%d elapsed=%.2fs",
            stats.get("n_entities", 0),
            stats.get("n_neighbors", 0),
            stats.get("n_relations", 0),
            stats.get("n_chunks", 0),
            elapsed,
        )

        return LocalRetrieverResult(
            question=question,
            identified_entities=identified,
            matched_entities=matched,
            subgraph_nodes=stats.get("n_neighbors", 0),
            subgraph_relations=stats.get("n_relations", 0),
            subgraph_chunks=stats.get("n_chunks", 0),
            answer=answer,
            elapsed_seconds=elapsed,
        )

    finally:
        if own_neo4j:
            neo4j.close()
