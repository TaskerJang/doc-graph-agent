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

관련 이슈: #13 (본 작업), #8 (Spike), #14 (NED — 본 모듈의 출력이 입력).
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

logger = logging.getLogger(__name__)


# ── 상수 ─────────────────────────────────────────────────────
# 청크 수에 비해 충분히 여유 있게 — Kimi 글로벌 엔드포인트 rate limit 기준.
# 너무 높으면 429, 너무 낮으면 처리 시간 ↑ . 운영하며 조정.
MAX_CONCURRENT = 8

# Entity 추출은 정밀 작업 — 회사 레포(0.3) 보다 한 단계 더 결정적으로.
TEMPERATURE = 0.2

# 청크 1개당 응답 상한 — Layer B 5타입 × 평균 4~5개 + relations 여유.
MAX_TOKENS_PER_CHUNK = 1500

# 프롬프트 경로 (회사 레포의 PROMPTS_DIR 패턴 차용)
PROMPTS_DIR              = Path(__file__).parent / "prompts"
SYSTEM_PROMPT_PATH       = PROMPTS_DIR / "entity_system_v1.md"
EXTRACT_PROMPT_PATH      = PROMPTS_DIR / "entity_extract_v1.md"


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

    chunk dict 예상 키: doc_id, section, text. 결측 시 placeholder 로 graceful.
    Semaphore 로 동시성 제한 + asyncio.to_thread 로 sync LLMClient 감쌈.
    """
    doc_id  = chunk.get("doc_id", "(unknown)")
    section = chunk.get("section") or "(no section)"
    text    = (chunk.get("text") or "").strip()

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

    try:
        data = _parse_extraction_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "JSON 파싱 실패 (doc=%s section=%s): %s | raw=%r",
            doc_id, section, exc, raw[:200],
        )
        return ExtractionResult()

    result = _coerce_to_result(data, section=section)
    logger.info(
        "추출 OK doc=%s section=%s entities=%d relations=%d (%.2fs)",
        doc_id, section, len(result.entities), len(result.relations), elapsed,
    )
    return result


# ── 공개 인터페이스 ──────────────────────────────────────────
async def extract(
    chunks: list[dict[str, Any]],
    llm: LLMClient | None = None,
) -> ExtractionResult:
    """문서 N 청크 → 통합 ExtractionResult.

    - 청크별로 병렬 추출 (Semaphore 제한)
    - 결과는 entities/relations 모두 평탄화하여 합침
    - local_id 는 청크 내에서만 유효 → 호출자(NED #14)가 청크 경계 알아야 함
      대안: prefix 부여 (`{chunk_idx}__{local_id}`) — 본 작업은 단순 합침으로,
      NED 단계에서 청크 경계 처리.

    DoD (#13):
    - 빈 청크 / 인식 실패 청크 graceful (KeyError 등 X)
    - 추출 결과를 #14 NED 의 입력으로 그대로 사용 가능
    """
    if not chunks:
        return ExtractionResult()

    llm            = llm or LLMClient()
    system_prompt  = _load_prompt(SYSTEM_PROMPT_PATH)
    extract_tmpl   = _load_prompt(EXTRACT_PROMPT_PATH)

    started = time.perf_counter()
    logger.info(
        "Entity 추출 시작 — 청크 %d개  MAX_CONCURRENT=%d  model=%s",
        len(chunks), MAX_CONCURRENT, llm.config.model,
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
    return merged
