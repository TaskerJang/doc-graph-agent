"""Layer B Entity 추출기 — Chunk → ExtractionResult.

회사 레포 `doc-summary-agent/summarizer/llm.py` 의 Map-Reduce + Semaphore
패턴을 doc-graph-agent 로 포팅. 두 가지 차이점:

1. **요약 → Entity 추출**로 작업 변경 (출력 스키마는 ExtractionResult)
2. **AsyncOpenAI 직접 사용 → LLMClient (sync) + asyncio.to_thread** 로 감쌈
   (`agent/llm_client.py` 가 OpenAI SDK 동기 클라이언트로 thin wrap 되어
    있어 그대로 재활용. Spike #8 에서 검증된 인터페이스.)

Spike (#8) 시행착오 박제:
- f-string + .format() 이중 처리는 절대 금지 → 일반 문자열 + .format() 으로 통일
- 프롬프트 안의 JSON 예시는 {{...}} 로 escape (entity_extract_v1.md 참조)
- LLM JSON 응답은 코드펜스 / 작은따옴표 등 변종 방어 코드 필수

#24 (Opik 트레이싱):
- 공개 진입점 `extract` 에 `@track` 부착 — Opik UI 에서 청크 수·소요·실패율 가시화.
- 청크 단위 (_extract_chunk) 는 의도적으로 부착 안 함 — 8문서 × N청크 일괄
  적재 시 trace 가 폭발하지 않도록. 필요하면 W5 에서 추가.

#17 (5/16 8문서 일괄 적재) — local_id 충돌 해결:
- 청크 N 개에서 각각 `ent_001` 부터 부여 → 다중 청크 시 local_id 충돌
- 해결 (옵션 3): chunk dict 에 옵셔널 `chunk_id` 키를 추가하면 본 모듈이
  자동으로 모든 entity local_id 와 relation source/target 에
  `{chunk_id}__{local_id}` prefix 부여 — global 유일성 확보.
- chunk_id 없는 호출 (5/10 두산밥캣 1청크 sanity) 은 기존 동작 그대로.

관련 이슈: #13 (본 작업), #8 (Spike), #14 (NED — 본 모듈의 출력이 입력),
          #17 (8문서 일괄), #24 (Opik 트레이싱).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.llm_client import LLMClient
from kg.ontology import (
    EntityType,
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
    RelationType,
)
from observability.tracing import track

logger = logging.getLogger(__name__)


# ── 상수 ─────────────────────────────────────────────────────
# 청크 수에 비해 충분히 여유 있게 — Kimi 글로벌 엔드포인트 rate limit 기준.
# 너무 높으면 429, 너무 낮으면 처리 시간 ↑ . 운영하며 조정.
MAX_CONCURRENT = 8

# Entity 추출은 정밀 작업 — 회사 레포(0.3) 보다 한 단계 더 결정적으로.
TEMPERATURE = 0.2

# 청크 1개당 응답 상한. 수치가 빽빽한 금융 청크는 Entity + source_span 이 길어
# 1500 으로는 JSON 이 잘리고(→ 파싱 실패 → 빈 결과 조용히 drop) 추출이 0건이 되는
# 사례 확인 (P1 #56, 두산밥캣 리포트). chat() 기본값(2048)보다 넉넉히 4000 으로 상향.
MAX_TOKENS_PER_CHUNK = 4000

# 프롬프트 경로 (회사 레포의 PROMPTS_DIR 패턴 차용)
PROMPTS_DIR              = Path(__file__).parent / "prompts"
SYSTEM_PROMPT_PATH       = PROMPTS_DIR / "entity_system_v2.md"
EXTRACT_PROMPT_PATH      = PROMPTS_DIR / "entity_extract_v2.md"

# local_id global prefix 구분자.
# `{chunk_id}__{local_id}` 의 `__` — '_' 단일은 chunk_id 안에 흔히 등장 (예:
# `doc_abc:c0001`) 하므로 충돌 회피 위해 이중 underscore.
_GLOBAL_ID_SEP = "__"


# ── 모듈 레벨 Semaphore (이벤트 루프 생명주기 공유) ──────────
_sem: asyncio.Semaphore | None = None


def _get_sem() -> asyncio.Semaphore:
    """실행 중인 이벤트 루프에서 Semaphore 를 지연 초기화한다.

    회사 레포 동일 패턴. 모듈 import 시점에 만들면 다른 이벤트 루프에서
    재사용 시 RuntimeError 가 나서 lazy init 가 안전.
    """
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(MAX_CONCURRENT)
    return _sem


# ── 프롬프트 로드 ────────────────────────────────────────────
def _load_prompt(path: Path) -> str:
    """프롬프트 파일을 읽는다. 캐시 안 하는 이유: hot-reload 가능하게."""
    return path.read_text(encoding="utf-8")


# ── JSON 파싱 방어 코드 ──────────────────────────────────────
# 회사 레포 chunk_summary 의 코드펜스 / 작은따옴표 처리 패턴을 그대로 차용.
_CODEFENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_codefence(raw: str) -> str:
    """LLM 이 가끔 ```json ... ``` 로 감싸는 경우 제거."""
    raw = raw.strip()
    m = _CODEFENCE_RE.match(raw)
    return m.group(1).strip() if m else raw


def _parse_extraction_json(raw: str) -> dict[str, Any]:
    """LLM raw 응답 → dict. 1차 실패 시 흔한 오류 보정 후 재시도.

    Spike (#8) 에서는 단순 json.loads 만 했는데 Kimi 가 가끔
    JSON 안 작은따옴표를 섞어 반환. 회사 레포의 정규식 보정을 차용.
    """
    cleaned = _strip_codefence(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # 큰따옴표 안의 작은따옴표 escape 시도 (회사 레포 동일 패턴)
        fixed = re.sub(r'(?<=: ")([^"]*)\'([^"]*?)(?=")', r"\1\'\2", cleaned)
        return json.loads(fixed)  # 두 번째도 실패하면 호출자가 잡음


# ── chunk_id prefix 부여 (옵션 3 — #17) ──────────────────────
def make_global_id(chunk_id: str, local_id: str) -> str:
    """`{chunk_id}__{local_id}` 형식의 global id 생성.

    역방향 파싱 (`parse_global_id`) 으로 어느 청크에서 나온 entity 인지
    추적 가능 — Layer A 의 `(:Chunk) -[:MENTIONS]-> (:Entity)` 매핑에 사용.
    """
    return f"{chunk_id}{_GLOBAL_ID_SEP}{local_id}"


def parse_global_id(global_id: str) -> tuple[str | None, str]:
    """global id 를 (chunk_id, local_id) 로 분해.

    prefix 가 없는 (구식) id 는 (None, id) 로 반환 — 5/10 두산밥캣 1청크
    sanity 와 호환.
    """
    if _GLOBAL_ID_SEP in global_id:
        chunk_id, local_id = global_id.split(_GLOBAL_ID_SEP, 1)
        return chunk_id, local_id
    return None, global_id


def _apply_chunk_id_prefix(
    result: ExtractionResult, chunk_id: str
) -> ExtractionResult:
    """ExtractionResult 의 모든 local_id / source / target 에 chunk_id prefix.

    `_coerce_to_result` 가 source/target 의 local_id 유효성 검증을 마친 후
    호출되므로, 본 함수는 매핑만 안전하게 수행.
    """
    if not chunk_id:
        return result

    # entity: local_id 만 prefix 부여
    new_entities = [
        ExtractedEntity(
            local_id=make_global_id(chunk_id, e.local_id),
            type=e.type,
            canonical=e.canonical,
            source_span=e.source_span,
            section=e.section,
        )
        for e in result.entities
    ]

    # relation: source / target 둘 다 prefix (같은 청크 내 관계만 추출되므로
    # 동일 chunk_id 로 prefix).
    new_relations = [
        ExtractedRelation(
            source=make_global_id(chunk_id, r.source),
            type=r.type,
            target=make_global_id(chunk_id, r.target),
            evidence=r.evidence,
        )
        for r in result.relations
    ]

    return ExtractionResult(entities=new_entities, relations=new_relations)


# ── 응답 → Pydantic 변환 ─────────────────────────────────────
def _coerce_to_result(data: dict[str, Any], section: str | None) -> ExtractionResult:
    """JSON dict → ExtractionResult.

    - 알 수 없는 EntityType / RelationType 은 graceful drop (시행착오 노트).
    - section 필드는 LLM 이 빼먹어도 호출 시점 값으로 fallback.
    - 관계의 source/target 이 entities 의 local_id 에 없으면 drop.
    """
    valid_entities: list[ExtractedEntity] = []
    dropped_entities: list[dict] = []

    for raw_e in data.get("entities", []):
        try:
            # section 미기재 시 fallback
            raw_e.setdefault("section", section)
            ent = ExtractedEntity(**raw_e)
        except (ValueError, TypeError) as exc:
            dropped_entities.append({"raw": raw_e, "reason": str(exc)})
            continue
        if ent.type not in EntityType:
            dropped_entities.append({"raw": raw_e, "reason": "unknown EntityType"})
            continue
        valid_entities.append(ent)

    if dropped_entities:
        logger.warning(
            "Entity drop %d 건 (section=%r): %s",
            len(dropped_entities),
            section,
            dropped_entities,
        )

    valid_ids = {e.local_id for e in valid_entities}
    valid_relations: list[ExtractedRelation] = []
    dropped_relations: list[dict] = []

    for raw_r in data.get("relations", []):
        try:
            rel = ExtractedRelation(**raw_r)
        except (ValueError, TypeError) as exc:
            dropped_relations.append({"raw": raw_r, "reason": str(exc)})
            continue
        if rel.type not in RelationType:
            dropped_relations.append({"raw": raw_r, "reason": "unknown RelationType"})
            continue
        if rel.source not in valid_ids or rel.target not in valid_ids:
            dropped_relations.append(
                {"raw": raw_r, "reason": "source/target not in entity local_ids"}
            )
            continue
        valid_relations.append(rel)

    if dropped_relations:
        logger.warning(
            "Relation drop %d 건 (section=%r): %s",
            len(dropped_relations),
            section,
            dropped_relations,
        )

    return ExtractionResult(entities=valid_entities, relations=valid_relations)


# ── LLM 호출 (재시도 데코레이터로 감쌈) ───────────────────────
@retry(
    retry=retry_if_exception_type(Exception),  # Spike 단계 — 광범위. W5 에서 좁힐 것.
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _call_llm(llm: LLMClient, system_prompt: str, user_prompt: str) -> str:
    """단일 청크에 대한 LLM 호출 (sync).

    LLMClient.chat 자체가 tenacity 로 감싸져 있지만, 본 함수는 JSON 파싱
    실패 후 재시도까지 포함하기 위해 한 번 더 감쌈.
    """
    return llm.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS_PER_CHUNK,
        response_format={"type": "json_object"},
    )


# ── 청크 1개 추출 (Map 단계) ──────────────────────────────────
async def _extract_chunk(
    llm: LLMClient,
    chunk: dict[str, Any],
    system_prompt: str,
    extract_template: str,
) -> ExtractionResult:
    """Chunk → ExtractionResult.

    chunk dict 예상 키: doc_id, section, text, (optional) chunk_id.
    결측 시 placeholder 로 graceful.
    chunk_id 가 있으면 결과의 local_id 들에 자동으로 prefix 부여 (#17).
    """
    doc_id   = chunk.get("doc_id", "(unknown)")
    section  = chunk.get("section") or "(no section)"
    text     = (chunk.get("text") or "").strip()
    chunk_id = chunk.get("chunk_id")  # #17 — global id prefix 용 (없으면 prefix 안 함)

    if not text:
        logger.info("빈 청크 skip (doc=%s section=%s)", doc_id, section)
        return ExtractionResult()

    user_prompt = extract_template.format(doc_id=doc_id, section=section, text=text)

    started = time.perf_counter()
    async with _get_sem():
        try:
            raw = await asyncio.to_thread(
                _call_llm, llm, system_prompt, user_prompt
            )
        except Exception as exc:
            logger.warning(
                "LLM 호출 실패 (doc=%s section=%s): %s", doc_id, section, exc
            )
            return ExtractionResult()

    elapsed = time.perf_counter() - started

    # llm_client 가 빈 content(또는 CoT 누출)를 '[답변 불가]' 로 정규화해 돌려준다.
    # 이는 정상적인 '추출할 Entity 없음'(valid empty JSON)과 다른 '하드 실패'이므로
    # 조용한 빈 결과로 묻지 말고 ERROR 로 드러낸다 (P1 #56 — 깨진 그래프 가시화).
    if raw.strip() == "[답변 불가]":
        logger.error(
            "추출 빈 응답 (doc=%s chunk=%s section=%s) — 토큰 부족/CoT 누출 의심. "
            "0건 처리. MAX_TOKENS_PER_CHUNK/모델 점검 필요.",
            doc_id, chunk_id or "(no-id)", section,
        )
        return ExtractionResult()

    try:
        data = _parse_extraction_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "JSON 파싱 실패 (doc=%s section=%s): %s | raw=%r",
            doc_id, section, exc, raw[:200],
        )
        return ExtractionResult()

    result = _coerce_to_result(data, section=section)

    # #17 — chunk_id 가 주어지면 global id prefix. 없으면 (5/10 sanity) 원본 그대로.
    if chunk_id:
        result = _apply_chunk_id_prefix(result, chunk_id)

    logger.info(
        "추출 OK doc=%s chunk=%s section=%s entities=%d relations=%d (%.2fs)",
        doc_id, chunk_id or "(no-id)", section,
        len(result.entities), len(result.relations), elapsed,
    )
    return result


# ── 공개 인터페이스 ──────────────────────────────────────────
@track
async def extract(
    chunks: list[dict[str, Any]],
    llm: LLMClient | None = None,
) -> ExtractionResult:
    """문서 N 청크 → 통합 ExtractionResult.

    - 청크별로 병렬 추출 (Semaphore 제한)
    - 결과는 entities/relations 모두 평탄화하여 합침
    - **chunk dict 에 옵셔널 `chunk_id` 키가 있으면** 본 모듈이 자동으로
      모든 entity local_id 와 relation source/target 에
      `{chunk_id}__{local_id}` prefix 부여 → 청크 간 global 유일성 (#17).
      없으면 (5/10 sanity 호환) 원본 local_id 유지.

    DoD (#13):
    - 빈 청크 / 인식 실패 청크 graceful (KeyError 등 X)
    - 추출 결과를 #14 NED 의 입력으로 그대로 사용 가능

    #24 Opik:
    - 본 함수에 `@track` — span 입출력은 청크 수 / Entity·Relation 수.
    - 환경 미설정 시 자동 no-op (`observability/tracing.py` 참조).
    """
    if not chunks:
        return ExtractionResult()

    llm            = llm or LLMClient()
    system_prompt  = _load_prompt(SYSTEM_PROMPT_PATH)
    extract_tmpl   = _load_prompt(EXTRACT_PROMPT_PATH)

    started = time.perf_counter()
    has_chunk_id = any(c.get("chunk_id") for c in chunks)
    logger.info(
        "Entity 추출 시작 — 청크 %d개  MAX_CONCURRENT=%d  model=%s  global_id=%s",
        len(chunks), MAX_CONCURRENT, llm.config.model,
        "ON" if has_chunk_id else "off",
    )

    results: list[ExtractionResult] = await asyncio.gather(
        *[_extract_chunk(llm, c, system_prompt, extract_tmpl) for c in chunks]
    )

    merged = ExtractionResult(
        entities=[e for r in results for e in r.entities],
        relations=[rel for r in results for rel in r.relations],
    )

    elapsed = time.perf_counter() - started
    failed = sum(1 for r in results if not r.entities and not r.relations)
    logger.info(
        "Entity 추출 완료 — 청크 %d개  total entities=%d relations=%d "
        "fail=%d  (%.2fs)",
        len(chunks), len(merged.entities), len(merged.relations), failed, elapsed,
    )
    if chunks and failed / len(chunks) >= 0.3:
        logger.warning(
            "추출 실패/빈결과율 %.0f%% (%d/%d 청크) — 그래프가 불완전할 수 있음. "
            "토큰·모델·파싱 점검 후 재인제스트 권장 (P1 #56).",
            100 * failed / len(chunks), failed, len(chunks),
        )
    return merged
