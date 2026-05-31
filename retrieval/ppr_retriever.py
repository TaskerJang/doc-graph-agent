"""PPR Retriever — Personalized PageRank 기반 멀티홉 검색 (HippoRAG식, Layer B+).

local_retriever(#19) 의 "엔티티 → **딱 1-hop** MENTIONS → 청크" 병목을 깨기 위한
retriever. 쿼리 엔티티를 seed 로 두고 엔티티 그래프 위에서 Personalized PageRank
(활성화 확산)를 돌려, *멀리 떨어진* 엔티티의 청크까지 후보 풀에 넣는다.

왜 만들었나 (근거):
- 3편 측정에서 local 의 "확인 불가"(subgraph 에 답 청크 없음)가 GraphRAG 최대
  AC-1 덩어리(~11문항)였다. 원인은 답 청크가 seed 엔티티에 1-hop 으로 안 매달려
  있어서. PPR 은 관계망을 따라 활성화를 퍼뜨려 이 한계를 구조적으로 깬다.
- HippoRAG (Gutiérrez et al., NeurIPS'24): LLM + KG + Personalized PageRank 로
  multi-hop QA 에서 기존 RAG 대비 큰 우위. 활성화가 그래프로 퍼지므로 쿼리 단어가
  하나도 없는 청크라도 엔티티 체인으로 강하게 연결돼 있으면 도달 — multi-hop 의 본질.

왜 networkx 인가 (GDS 아님):
- 본 그래프는 ~610 노드 / ~2,451 관계로 작다. networkx PPR 은 수 ms.
- 표준 Neo4j GDS 는 Enterprise 전용. DozerDB 의 OpenGDS 는 버전 매칭이 까다롭다
  (ClassNotFoundException: MetricsManager 등). 이 규모에선 인프라 의존 0 인
  networkx 가 더 빠르고 투명. GDS 는 그래프가 수만 노드로 커질 때.

흐름:
  자연어 질문
     ↓ _identify_entities + _match_entities (local 재사용 — seed 엔티티 확보)
  seed 엔티티 노드
     ↓ _load_entity_graph (Neo4j → networkx, 캐시) — 엔티티-엔티티(Layer B + co-mention)
  엔티티 그래프 (가중 무방향)
     ↓ _run_ppr (seed 에 personalization 집중)
  엔티티별 PPR 점수
     ↓ _rank_chunks (상위 엔티티의 MENTIONS 청크를 PPR 합으로 점수)
  top-k 청크
     ↓ _generate_answer (LLM)
  자연어 답변

안전장치:
1. read-only — 모든 Cypher 는 조회 전용 + parameterized.
2. 결과 크기 제한 — TOP_ENTITIES / TOP_K_CHUNKS / CHUNK_TEXT_TRUNCATE.
3. graceful fallback — seed 0개 / 빈 그래프 / LLM 실패 모두 자연어 안내.

v1 범위 (지금):
- 엔티티 그래프 PPR + 청크 readout. HippoRAG 1편 본질.

v2 (나중, 측정 보고):
- dual-node (passage+phrase 노드를 PPR 그래프에 직접 포함, HippoRAG 2).
- node specificity (IDF 유사 — 희소 엔티티 seed 가중).
- dense seed (임베딩 유사 청크도 seed 에 추가 — dense+sparse 통합).

#24 Opik:
- 공개 진입점 `ppr_retrieve` 에 `@track`.

Reference:
- retrieval/local_retriever.py — entity 식별/매칭 front-end 재사용.
- HippoRAG (NeurIPS'24, arXiv 2405.14831) — KG + Personalized PageRank 멀티홉.
- HippoRAG 2 (2025) — dual-node + dense/sparse 통합 (v2 참고).
- Cormack et al. 2009 (RRF) — 추후 bm25 ⊕ ppr 융합 시 (Plan B).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.llm_client import LLMClient
from kg.neo4j_client import Neo4jClient
from observability.tracing import track

# local 의 entity 식별/매칭 front-end 재사용 (DRY — v1 은 동일 seed 로직)
from retrieval.local_retriever import (
    ENTITY_PROMPT_PATH,
    _identify_entities,
    _load_prompt,
    _match_entities,
)

logger = logging.getLogger(__name__)


# ── 상수 ─────────────────────────────────────────────────────
TEMPERATURE_ANSWER = 0.3
MAX_TOKENS_ANSWER = 700

PPR_ALPHA = 0.85              # PageRank damping (HippoRAG 기본값 계열)
TOP_ENTITIES = 15            # PPR 상위 엔티티 중 청크 수집 대상
TOP_K_CHUNKS = 8             # 최종 답변에 넘길 청크 수 (bm25 와 동일)
CHUNK_TEXT_TRUNCATE = 600    # 청크 1개당 char 상한
MAX_CHUNK_ROWS = 5000        # entity→chunk 풀 안전 상한

# Layer B 관계 (local 과 일치)
LAYER_B_RELS = ("FACES_RISK", "HAS_METRIC", "HAS_OUTLOOK", "RECOMMENDED_FOR")

PROMPTS_DIR = Path(__file__).parent / "prompts"
ANSWER_PROMPT_PATH = PROMPTS_DIR / "ppr_answer_v1.md"

# 엔티티 그래프 캐시 — 그래프는 한 run 동안 정적이므로 1회만 빌드.
# (eval 80 QA 가 매번 그래프를 다시 안 끌어오게.) rebuild=True 로 무효화.
_GRAPH_CACHE: dict[str, Any] = {}


# ── 결과 객체 ────────────────────────────────────────────────
@dataclass
class PPRRetrieverResult:
    """PPR retriever 한 회차의 전체 trace."""

    question: str
    identified_entities: list[dict[str, Any]] = field(default_factory=list)
    matched_entities: list[dict[str, Any]] = field(default_factory=list)
    seed_names: list[str] = field(default_factory=list)
    n_graph_nodes: int = 0
    n_graph_edges: int = 0
    top_entities: list[dict[str, Any]] = field(default_factory=list)  # [{name, score}]
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    n_chunks: int = 0
    retrieved_context: str = ""   # E1: faithfulness judge 대조용 (청크 text join)
    answer: str = ""
    elapsed_seconds: float = 0.0
    error: str | None = None


# ── Cypher (read-only) ───────────────────────────────────────
_ENTITIES_CYPHER = """
MATCH (e:Entity)
RETURN elementId(e) AS id, e.name AS name, labels(e) AS labels
LIMIT 100000
"""

_RELS_CYPHER = """
MATCH (a:Entity)-[r]-(b:Entity)
WHERE type(r) IN $rel_types AND elementId(a) < elementId(b)
RETURN elementId(a) AS src, elementId(b) AS dst, count(r) AS weight
LIMIT 1000000
"""

_COMENTION_CYPHER = """
MATCH (a:Entity)<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(b:Entity)
WHERE elementId(a) < elementId(b)
RETURN elementId(a) AS src, elementId(b) AS dst, count(DISTINCT c) AS weight
LIMIT 1000000
"""

_CHUNKS_CYPHER = """
MATCH (e:Entity)<-[:MENTIONS]-(c:Chunk)
RETURN elementId(e) AS eid,
       c.id AS chunk_id,
       substring(c.text, 0, $truncate) AS text,
       properties(c).page AS page
LIMIT $max_rows
"""


# ── 그래프 구성 (검증된 순수 함수) ──────────────────────────
def _build_entity_graph(
    entity_rows: list[dict[str, Any]],
    rel_rows: list[dict[str, Any]],
    comention_rows: list[dict[str, Any]],
) -> nx.Graph:
    """엔티티 그래프 구성 (무방향 가중). 엣지 weight = 관계/co-mention 누적."""
    G = nx.Graph()
    for e in entity_rows:
        G.add_node(e["id"], name=e.get("name") or "", labels=e.get("labels") or [])

    def _add(src: str, dst: str, w: float) -> None:
        if not src or not dst or src == dst or src not in G or dst not in G:
            return
        if G.has_edge(src, dst):
            G[src][dst]["weight"] += w
        else:
            G.add_edge(src, dst, weight=w)

    for r in rel_rows:
        _add(r.get("src"), r.get("dst"), float(r.get("weight", 1) or 1))
    for r in comention_rows:
        _add(r.get("src"), r.get("dst"), float(r.get("weight", 1) or 1))
    return G


def _run_ppr(G: nx.Graph, seed_ids: list[str]) -> dict[str, float]:
    """seed 노드에 personalization 집중한 Personalized PageRank."""
    seeds = [s for s in seed_ids if s in G]
    if G.number_of_nodes() == 0 or not seeds:
        return {}
    personalization = {n: 0.0 for n in G.nodes}
    for s in seeds:
        personalization[s] = 1.0 / len(seeds)
    try:
        return nx.pagerank(
            G, alpha=PPR_ALPHA, personalization=personalization, weight="weight"
        )
    except nx.PowerIterationFailedConvergence as exc:
        logger.warning("PPR 수렴 실패: %s — 균등 fallback", exc)
        return nx.pagerank(G, alpha=PPR_ALPHA, weight="weight")


def _rank_chunks(
    pr: dict[str, float],
    chunk_rows: list[dict[str, Any]],
    top_entities: int = TOP_ENTITIES,
    top_k_chunks: int = TOP_K_CHUNKS,
) -> list[dict[str, Any]]:
    """상위 활성 엔티티의 청크를 'PPR 합'으로 점수매겨 top-k.

    chunk score = 그 청크를 언급한 (상위) 엔티티들의 PPR 점수 합.
    """
    if not pr:
        return []
    ranked_ents = sorted(pr.items(), key=lambda kv: kv[1], reverse=True)[:top_entities]
    top_set = {eid for eid, _ in ranked_ents}

    chunk_score: dict[str, float] = {}
    chunk_meta: dict[str, dict[str, Any]] = {}
    for row in chunk_rows:
        eid = row.get("eid")
        if eid not in top_set:
            continue
        cid = row.get("chunk_id")
        text = row.get("text")
        if not cid or not text:
            continue
        chunk_score[cid] = chunk_score.get(cid, 0.0) + pr.get(eid, 0.0)
        if cid not in chunk_meta:
            chunk_meta[cid] = {"chunk_id": cid, "text": text, "page": row.get("page")}

    ranked = sorted(chunk_score.items(), key=lambda kv: kv[1], reverse=True)[:top_k_chunks]
    out: list[dict[str, Any]] = []
    for cid, score in ranked:
        m = dict(chunk_meta[cid])
        m["ppr_score"] = round(score, 5)
        out.append(m)
    return out


# ── 그래프 로드 (Neo4j → networkx, 캐시) ────────────────────
def _load_entity_graph(
    neo4j: Neo4jClient, rebuild: bool = False
) -> tuple[nx.Graph, list[dict[str, Any]]]:
    """엔티티 그래프 + entity→chunk rows 를 Neo4j 에서 1회 빌드 후 캐시.

    Returns:
        (G, chunk_rows). 실패 시 (빈 그래프, []).
    """
    if not rebuild and "graph" in _GRAPH_CACHE:
        return _GRAPH_CACHE["graph"], _GRAPH_CACHE["chunk_rows"]

    try:
        entity_rows = neo4j.read(_ENTITIES_CYPHER)
        rel_rows = neo4j.read(_RELS_CYPHER, rel_types=list(LAYER_B_RELS))
        comention_rows = neo4j.read(_COMENTION_CYPHER)
        chunk_rows = neo4j.read(
            _CHUNKS_CYPHER, truncate=CHUNK_TEXT_TRUNCATE, max_rows=MAX_CHUNK_ROWS
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("엔티티 그래프 로드 실패: %s", exc)
        return nx.Graph(), []

    G = _build_entity_graph(entity_rows, rel_rows, comention_rows)
    _GRAPH_CACHE["graph"] = G
    _GRAPH_CACHE["chunk_rows"] = chunk_rows
    logger.info(
        "엔티티 그래프 빌드 — %d 노드 / %d 엣지 / chunk_rows=%d",
        G.number_of_nodes(), G.number_of_edges(), len(chunk_rows),
    )
    return G, chunk_rows


# ── 답변 생성 ────────────────────────────────────────────────
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


def _generate_answer(
    llm: LLMClient,
    question: str,
    chunks: list[dict[str, Any]],
    top_entities: list[dict[str, Any]],
    answer_system_prompt: str,
    note: str = "",
) -> str:
    """질문 + PPR 청크 → 자연어 답변. 0건/실패 모두 LLM 에 넘겨 안내."""
    user_payload = {
        "question": question,
        "retrieved_chunks": chunks,
        "activated_entities": top_entities,
        "note": note,
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)
    try:
        answer = _call_llm_text(llm, answer_system_prompt, user_prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PPR 답변 생성 LLM 호출 실패: %s", exc)
        if not chunks:
            return note or "검색된 자료에서 답을 찾지 못했습니다."
        return f"{len(chunks)}개 청크를 검색했으나 자연어 변환에 실패했습니다."
    return answer.strip()


# ── 공개 인터페이스 ──────────────────────────────────────────
@track
def ppr_retrieve(
    question: str,
    llm: LLMClient | None = None,
    neo4j: Neo4jClient | None = None,
    rebuild_graph: bool = False,
) -> PPRRetrieverResult:
    """자연어 질문 → seed 엔티티 → PPR → 상위 엔티티 청크 → 자연어 답변.

    Args:
        question: 사용자 자연어 질문.
        llm: 테스트용 mock 주입 가능. 기본 LLMClient().
        neo4j: 테스트용 mock 주입 가능. 기본 Neo4jClient().
        rebuild_graph: True 면 캐시 무시하고 그래프 재빌드.

    Returns:
        PPRRetrieverResult — 전체 trace 포함. answer 는 항상 채워짐.
    """
    started = time.perf_counter()
    if not question or not question.strip():
        return PPRRetrieverResult(
            question=question,
            answer="질문이 비어 있습니다. 그래프에 대해 궁금한 점을 입력해 주세요.",
            elapsed_seconds=time.perf_counter() - started,
        )

    llm = llm or LLMClient()
    own_neo4j = neo4j is None
    neo4j = neo4j or Neo4jClient()

    entity_system_prompt = _load_prompt(ENTITY_PROMPT_PATH)
    answer_system_prompt = _load_prompt(ANSWER_PROMPT_PATH)
    logger.info("PPRRetriever 시작 — question=%r", question)

    try:
        # 1) seed 엔티티 식별 + 매칭 (local front-end 재사용)
        identified, explanation = _identify_entities(
            llm, question, entity_system_prompt
        )
        matched = _match_entities(neo4j, identified) if identified else []
        seed_ids = list({m["id"] for m in matched})
        seed_names = [m["name"] for m in matched]

        # 2) 엔티티 그래프 (캐시)
        G, chunk_rows = _load_entity_graph(neo4j, rebuild=rebuild_graph)

        if not seed_ids or G.number_of_nodes() == 0:
            note = (
                explanation
                or "질문에서 그래프 seed 엔티티를 찾지 못했습니다."
                if not seed_ids
                else "엔티티 그래프가 비어 있습니다."
            )
            answer = _generate_answer(
                llm, question, [], [], answer_system_prompt, note=note
            )
            return PPRRetrieverResult(
                question=question,
                identified_entities=identified,
                matched_entities=matched,
                seed_names=seed_names,
                n_graph_nodes=G.number_of_nodes(),
                n_graph_edges=G.number_of_edges(),
                answer=answer,
                elapsed_seconds=time.perf_counter() - started,
                error=note,
            )

        # 3) Personalized PageRank
        pr = _run_ppr(G, seed_ids)

        # 4) 상위 엔티티 + 청크 readout
        ranked_ents = sorted(pr.items(), key=lambda kv: kv[1], reverse=True)[:TOP_ENTITIES]
        top_entities = [
            {"name": G.nodes[eid].get("name", ""), "score": round(s, 5)}
            for eid, s in ranked_ents
        ]
        chunks = _rank_chunks(pr, chunk_rows)
        context = "\n\n".join((c.get("text") or "") for c in chunks).strip()

        # 5) 답변 생성
        answer = _generate_answer(
            llm, question, chunks, top_entities, answer_system_prompt
        )

        elapsed = time.perf_counter() - started
        logger.info(
            "PPRRetriever 완료 — seeds=%d nodes=%d edges=%d chunks=%d elapsed=%.2fs",
            len(seed_ids), G.number_of_nodes(), G.number_of_edges(),
            len(chunks), elapsed,
        )
        return PPRRetrieverResult(
            question=question,
            identified_entities=identified,
            matched_entities=matched,
            seed_names=seed_names,
            n_graph_nodes=G.number_of_nodes(),
            n_graph_edges=G.number_of_edges(),
            top_entities=top_entities,
            retrieved_chunks=chunks,
            n_chunks=len(chunks),
            retrieved_context=context,
            answer=answer,
            elapsed_seconds=elapsed,
        )
    finally:
        if own_neo4j:
            neo4j.close()
