"""Text2Cypher — 자연어 질의 → Cypher → 결과 → 자연어 답변.

W4 첫 번째 retrieval 진입점 (#18). doc-ontology.md §3-§4 스키마를 LLM 프롬프트에
주입하고, 5/16 적재된 8문서 그래프 (610 노드 / 2,451 관계 / 1,189 MENTIONS)
위에서 동작.

흐름:
  자연어 질문
     ↓ _generate_cypher (LLM 1단계, JSON 응답)
  Cypher (또는 None — 스키마 외 질문)
     ↓ _enforce_safety (read-only + LIMIT 100 강제)
     ↓ Neo4jClient.read
  결과 (list[dict])
     ↓ _generate_answer (LLM 2단계, plain text 응답)
  자연어 답변

안전장치 (이슈 #18 DoD):
1. **read-only 강제**: CREATE/DELETE/SET/MERGE/REMOVE/DROP 키워드 포함 시 거부.
2. **LIMIT 100 강제**: 미명시 시 자동 부착 (Neo4jClient 가 이미 수행하지만 본
   모듈에서도 사전 검증해 사용자에게 빨리 피드백).
3. **graceful fallback**: LLM 이 cypher=null 반환 / Cypher 실행 실패 / 빈 결과
   모두 사용자에게 친절한 자연어로 안내.

#24 Opik:
- 공개 진입점 `text2cypher` 에 `@track` — 질문/Cypher/결과 크기/소요 trace.
- 환경 미설정 시 자동 no-op.

시행착오 박제 — 5/16 발견 자산 활용:
- Entity 라벨 품질 challenge (Company 186 중 진짜 회사명 1개) → answer 프롬프트가
  결과 검토 후 한 줄 정직하게 언급하도록 가이드 (text2cypher_answer_v1.md).
- 자기 회사 보고서에 자기 회사명 entity 없음 → '미래에셋증권 검색 시 빈 결과
  → 친절 안내' 패턴을 answer 프롬프트 예시에 박제.

Reference: kg/extractor.py 의 LLM 호출 / JSON 파싱 / 프롬프트 로드 패턴 그대로 차용.
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


# ── 상수 ─────────────────────────────────────────────────────
# Cypher 생성은 정밀 작업 — extractor 와 동일하게 결정적으로.
TEMPERATURE_GENERATE = 0.1

# 답변 생성은 자연스러운 한국어가 필요 — 약간 더 풀어줌.
TEMPERATURE_ANSWER = 0.3

MAX_TOKENS_GENERATE = 800
MAX_TOKENS_ANSWER = 600

# 결과를 LLM 답변 생성기에 넘길 때 너무 크면 토큰 폭발 — top N 만.
MAX_RESULT_ROWS_FOR_ANSWER = 30

# 프롬프트 경로 (extractor 와 동일 패턴)
PROMPTS_DIR = Path(__file__).parent / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "text2cypher_system_v1.md"
ANSWER_PROMPT_PATH = PROMPTS_DIR / "text2cypher_answer_v2.md"

# read-only 강제 — 본 모듈의 핵심 안전장치.
# Neo4jClient.read 도 강제하지만 본 모듈 단계에서 더 빨리 차단하는 게 좋음
# (잘못된 Cypher 가 driver 까지 안 가도록).
FORBIDDEN_KEYWORDS = (
    "CREATE",
    "DELETE",
    "DETACH",
    "SET",
    "REMOVE",
    "MERGE",
    "DROP",
    "CALL",  # APOC 등 write procedures 차단 (보수적)
    "LOAD",  # LOAD CSV 차단
)

_DEFAULT_LIMIT = 100


# ── 결과 객체 / 예외 ─────────────────────────────────────────
@dataclass
class Text2CypherResult:
    """Text2Cypher 한 회차의 전체 trace.

    Opik / Aura console 디버깅 시 모든 중간 산물 확인 가능.
    DoD: cypher 가 None 이거나 result 가 [] 이어도 answer 는 항상 채워짐
    (graceful fallback).
    """

    question: str
    cypher: str | None
    explanation: str
    result: list[dict] = field(default_factory=list)
    answer: str = ""
    elapsed_seconds: float = 0.0
    error: str | None = None


class Text2CypherError(Exception):
    """Text2Cypher 내부 오류. 보안 위반 등 호출자가 알아야 할 경우에만 raise.

    LLM 호출 실패 / 빈 결과 같이 자연어로 안내 가능한 케이스는 raise 하지 않고
    `Text2CypherResult.error` 에 메시지를 박아서 graceful 반환.
    """


# ── 프롬프트 로드 (extractor 와 동일 패턴 — hot-reload 가능하게 캐시 안 함) ──
def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── JSON 파싱 방어 (extractor 와 동일 패턴) ──────────────────
_CODEFENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_codefence(raw: str) -> str:
    raw = raw.strip()
    m = _CODEFENCE_RE.match(raw)
    return m.group(1).strip() if m else raw


def _parse_generate_json(raw: str) -> dict[str, Any]:
    """LLM 1단계 (Cypher 생성) 응답을 파싱.

    예상 형식:
      {"cypher": "..." | null, "explanation": "..."}
    """
    cleaned = _strip_codefence(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # extractor 와 동일 — 따옴표 escape 보정
        fixed = re.sub(r'(?<=: ")([^"]*)\'([^"]*?)(?=")', r"\1\'\2", cleaned)
        return json.loads(fixed)


# ── 안전장치 ────────────────────────────────────────────────
def _enforce_safety(cypher: str) -> str:
    """read-only 강제 + LIMIT 100 강제.

    Raises:
        Text2CypherError: 금지 키워드 포함 시.
    """
    # 1. read-only 검증 (case-insensitive, word boundary 로 false positive 최소화)
    upper = cypher.upper()
    for kw in FORBIDDEN_KEYWORDS:
        # word boundary — "CREATED" 같은 식별자 안의 부분 일치 회피.
        # Cypher 키워드는 토큰화되어 있으므로 정규식이 안전.
        if re.search(rf"\b{kw}\b", upper):
            raise Text2CypherError(
                f"금지된 키워드 포함: {kw}. read-only 쿼리만 허용됩니다."
            )

    # 2. LIMIT 강제 (Neo4jClient 도 강제하지만 명시적으로 한 번 더)
    if " LIMIT " not in upper:
        cypher = f"{cypher.rstrip().rstrip(';')} LIMIT {_DEFAULT_LIMIT}"
        logger.debug("LIMIT 미명시 → 자동 부착 (LIMIT %d)", _DEFAULT_LIMIT)

    return cypher


# ── LLM 호출 (재시도) ────────────────────────────────────────
@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _call_llm_json(llm: LLMClient, system_prompt: str, user_prompt: str) -> str:
    """LLM 1단계 — JSON 응답 강제."""
    return llm.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=TEMPERATURE_GENERATE,
        max_tokens=MAX_TOKENS_GENERATE,
        response_format={"type": "json_object"},
    )


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _call_llm_text(llm: LLMClient, system_prompt: str, user_prompt: str) -> str:
    """LLM 2단계 — plain text 응답."""
    return llm.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=TEMPERATURE_ANSWER,
        max_tokens=MAX_TOKENS_ANSWER,
    )


# ── 1단계: Cypher 생성 ──────────────────────────────────────
def _generate_cypher(
    llm: LLMClient, question: str, system_prompt: str
) -> tuple[str | None, str]:
    """질문 → (cypher | None, explanation).

    LLM 이 스키마 외 질문이라 판단하면 cypher=None 으로 graceful 반환.
    JSON 파싱 실패는 (None, error_msg) 로 graceful.
    """
    user_prompt = f"질문: {question}"
    try:
        raw = _call_llm_json(llm, system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("Cypher 생성 LLM 호출 실패: %s", exc)
        return None, f"LLM 호출 실패: {exc}"

    try:
        data = _parse_generate_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Cypher 응답 JSON 파싱 실패: %s | raw=%r", exc, raw[:200])
        return None, f"JSON 파싱 실패: {exc}"

    cypher = data.get("cypher")  # null 가능
    explanation = (data.get("explanation") or "").strip()

    if cypher is None:
        # LLM 이 의도적으로 거부한 케이스 — explanation 그대로 사용자에게 전달.
        logger.info("Cypher 생성 거부 (스키마 외 질문 등): %s", explanation)
        return None, explanation

    cypher = cypher.strip()
    if not cypher:
        return None, "빈 Cypher 반환됨"

    return cypher, explanation


# ── 2단계: 결과 → 자연어 답변 ────────────────────────────────
def _generate_answer(
    llm: LLMClient,
    question: str,
    cypher: str | None,
    result: list[dict],
    answer_system_prompt: str,
    fallback_explanation: str = "",
) -> str:
    """질문 + Cypher + 결과 → 자연어 답변.

    빈 결과 / cypher None 모두 LLM 에 그대로 넘겨서 자연스럽게 안내하게 함.
    토큰 절약을 위해 결과는 top-N 만.
    """
    truncated = result[:MAX_RESULT_ROWS_FOR_ANSWER]
    truncated_note = (
        f" (총 {len(result)}건 중 상위 {MAX_RESULT_ROWS_FOR_ANSWER}건만 전달)"
        if len(result) > MAX_RESULT_ROWS_FOR_ANSWER
        else ""
    )

    user_payload = {
        "question": question,
        "cypher": cypher,
        "result": truncated,
        "note": truncated_note,
        "fallback_explanation": fallback_explanation,
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)

    try:
        answer = _call_llm_text(llm, answer_system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("Answer 생성 LLM 호출 실패: %s", exc)
        # 최후의 fallback — LLM 답변마저 실패하면 raw 결과를 짧게 요약.
        if cypher is None:
            return f"질문에 답하기 어렵습니다. 이유: {fallback_explanation}"
        if not result:
            return "해당 조건에 맞는 결과를 찾지 못했습니다."
        return f"총 {len(result)}건의 결과를 찾았습니다 (자연어 변환 실패)."

    return answer.strip()


# ── 공개 인터페이스 ──────────────────────────────────────────
@track
def text2cypher(
    question: str,
    llm: LLMClient | None = None,
    neo4j: Neo4jClient | None = None,
) -> Text2CypherResult:
    """자연어 질문 → Cypher → 결과 → 자연어 답변.

    DoD (#18):
    - 'X 문서의 Y 섹션에 무엇이 있나' 류 질문에 답변 생성
    - 잘못된 Cypher 생성 시 graceful fallback (빈 결과 + 안내)
    - read-only 강제 + LIMIT 100 강제

    Args:
        question: 사용자 자연어 질문.
        llm: LLMClient (테스트용 mock 주입 가능). 미지정 시 기본 생성.
        neo4j: Neo4jClient (테스트용 mock 주입 가능). 미지정 시 기본 생성.

    Returns:
        Text2CypherResult — 전체 trace 포함. answer 는 항상 채워짐.
    """
    if not question or not question.strip():
        return Text2CypherResult(
            question=question,
            cypher=None,
            explanation="",
            answer="질문이 비어 있습니다. 그래프에 대해 궁금한 점을 입력해 주세요.",
        )

    llm = llm or LLMClient()
    own_neo4j = neo4j is None  # 본 함수가 만든 경우만 close
    neo4j = neo4j or Neo4jClient()

    system_prompt = _load_prompt(SYSTEM_PROMPT_PATH)
    answer_system_prompt = _load_prompt(ANSWER_PROMPT_PATH)

    started = time.perf_counter()
    logger.info("Text2Cypher 시작 — question=%r", question)

    try:
        # 1단계: Cypher 생성
        cypher, explanation = _generate_cypher(llm, question, system_prompt)

        if cypher is None:
            # 스키마 외 질문 / JSON 파싱 실패 등 — LLM 답변기로 자연스럽게 안내.
            answer = _generate_answer(
                llm, question, None, [], answer_system_prompt,
                fallback_explanation=explanation,
            )
            elapsed = time.perf_counter() - started
            logger.info(
                "Text2Cypher 완료 (cypher 없음) elapsed=%.2fs", elapsed
            )
            return Text2CypherResult(
                question=question,
                cypher=None,
                explanation=explanation,
                result=[],
                answer=answer,
                elapsed_seconds=elapsed,
            )

        # 2단계: 안전장치 통과 후 실행
        try:
            safe_cypher = _enforce_safety(cypher)
        except Text2CypherError as exc:
            logger.warning("안전장치 위반: %s | cypher=%r", exc, cypher)
            answer = (
                "보안 정책에 의해 해당 쿼리는 실행할 수 없습니다. "
                "조회(읽기) 질문만 처리합니다."
            )
            elapsed = time.perf_counter() - started
            return Text2CypherResult(
                question=question,
                cypher=cypher,
                explanation=explanation,
                result=[],
                answer=answer,
                elapsed_seconds=elapsed,
                error=str(exc),
            )

        # 3단계: Neo4j 실행
        try:
            result = neo4j.read(safe_cypher)
        except Exception as exc:
            logger.warning("Cypher 실행 실패: %s | cypher=%r", exc, safe_cypher)
            answer = (
                f"쿼리 실행 중 오류가 발생했습니다. 질문을 다르게 표현해 주시면 "
                f"다시 시도하겠습니다. (사유: {exc})"
            )
            elapsed = time.perf_counter() - started
            return Text2CypherResult(
                question=question,
                cypher=safe_cypher,
                explanation=explanation,
                result=[],
                answer=answer,
                elapsed_seconds=elapsed,
                error=str(exc),
            )

        # 4단계: 결과 → 자연어 답변
        answer = _generate_answer(
            llm, question, safe_cypher, result, answer_system_prompt
        )

        elapsed = time.perf_counter() - started
        logger.info(
            "Text2Cypher 완료 — rows=%d elapsed=%.2fs cypher=%r",
            len(result), elapsed, safe_cypher,
        )

        return Text2CypherResult(
            question=question,
            cypher=safe_cypher,
            explanation=explanation,
            result=result,
            answer=answer,
            elapsed_seconds=elapsed,
        )

    finally:
        if own_neo4j:
            neo4j.close()
