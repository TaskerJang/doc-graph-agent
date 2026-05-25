"""Routing Agent — 질문 유형에 따라 Layer A / B / C 로 분기 (#21).

W4 통합 진입점. 사용자 질문을 받아 세 retriever 중 하나로 라우팅:

- **Layer A** (`retrieval.text2cypher`) — factual / numerical / topN / 특정 문서
- **Layer B** (`retrieval.local_retrieve`) — 관계 / 연관 / co-mention / 단일 entity
- **Layer C** (`retrieval.community_summary`) — 글로벌 / 트렌드 / 전체 요약 (stub)

흐름:
  자연어 질문
     ↓ _classify_by_keywords (1단계 — 결정적 키워드 매칭)
  RouteDecision (route + matched_keywords + 신뢰도)
     │
     ├─ 매칭 있음 → 해당 retriever 즉시 호출
     └─ 매칭 없음 → _classify_by_llm (2단계 — LLM fallback)
           ↓
        RouteDecision (route + reasoning, llm_used=True)
           ↓
        해당 retriever 호출
  통합 답변 RoutedResult

설계 결정 (5/17 박제):
- **결정적 키워드 우선**: LangChain MultiRetrievalQAChain 의 LLM router 는 "the
  same query may route to different sources" (TDS, 2025) 라는 일관성 문제 있음.
  결정적 분기를 1단계로 두면 디버깅 / 평가 / 발표 시연 모두 명확.
- **LLM fallback 은 필요한 만큼만**: 키워드 미매칭 시에만 호출 → 토큰 비용
  최소화. 단순 factual 질문은 LLM 호출 없이 t2c 로 라우팅.
- **graceful default**: LLM 도 실패하면 → local (5/25 v2 갱신, 이전 t2c).

5/25 v2 박힘:
- DEFAULT_ROUTE: "t2c" → "local" 변경
- ROUTER_PROMPT_PATH: router_v1.md → router_v2.md 변경
- 단일 entity 사실 / 관계 / 속성 / 단일 문서 컨텍스트 모두 local 로 라우팅
- t2c 는 명백한 top-N / 집계 / 필터 / 메타데이터 비교에만 제한
- dryrun_80qa 결과 (VectorRAG 5/5 t2c rows=0 실패) 박제 후 결정

키워드 매핑 (5/17 결정):
- "관계 / 관련 / 연관 / 영향 / 함께 / 이웃 / 어떻게" → **local**
- "트렌드 / 전체 / 흐름 / 요약 / community / 글로벌 / 패턴 / 주제" → **community**
- 그 외 (factual / 몇 / 개수 / top / 특정 문서 등) → **local** (v2 default)

향후 확장 (5/24+):
- Semantic router (embedding 기반) 로 키워드 매칭의 어휘 한계 보완 가능
- LLM fallback 의 신뢰도 임계 (현재 binary) 를 점수화하여 dual-path 합성도 가능
- Conversation history 반영 (현재는 stateless)

#24 Opik:
- 공개 진입점 `route_and_answer` 에 `@track` — 질문/라우팅/소요 trace
- 내부 retriever 호출의 @track 과 nested span 으로 표시됨

Reference:
- LangChain MultiRetrievalQAChain — LLM 라우터 표준 패턴
- LangChain EmbeddingRouterChain (cookbook) — semantic router 표준
- Neo4j ToolsRetriever — convert_to_tool(name, description) 후 LLM 자동 선택
- NeoConverse — "specialized agent 없으면 Text2Cypher 로 graceful fallback"
- Sotaaz blog (2026-01) — hybrid_search() 의 if/elif/else 결정적 분기 패턴
- Memgraph Atomic GraphRAG (2026-03) — Analytical / Local / Global 3-way 분류
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.llm_client import LLMClient
from kg.neo4j_client import Neo4jClient
from observability.tracing import track
from retrieval.community_summary import CommunitySummaryResult, community_summary
from retrieval.local_retriever import LocalRetrieverResult, local_retrieve
from retrieval.text2cypher import Text2CypherResult, text2cypher

logger = logging.getLogger(__name__)


# ── 타입 ─────────────────────────────────────────────────────
Route = Literal["t2c", "local", "community"]


# ── 키워드 매핑 (5/17 결정) ──────────────────────────────────
# Local Retriever 신호 — 관계 / 연관 / co-mention 질의
LOCAL_KEYWORDS: tuple[str, ...] = (
    "관계",
    "관련",
    "연관",
    "영향",
    "함께",
    "이웃",
    "어떻게",
    "co-mention",
    "관계는",
    "관련된",
    "연관된",
)

# Community Summary 신호 — 글로벌 / 트렌드 / 전체 요약
COMMUNITY_KEYWORDS: tuple[str, ...] = (
    "트렌드",
    "전체",
    "흐름",
    "주요 트렌드",
    "주제",
    "패턴",
    "주요 흐름",
    "전반",
    "글로벌",
    "community",
    "communities",
    "topic",
    "topics",
    "themes",
    "전체적",
    "통합",
    "사전체",
)

# 기본 라우트 — 키워드 + LLM 모두 결정 못하면 여기로
# 5/25 v2: "t2c" → "local" 변경. 단일 entity 사실 질의가 압도적으로 많음을 반영.
DEFAULT_ROUTE: Route = "local"

# 프롬프트 경로 — 5/25 v2: router_v1.md → router_v2.md
PROMPTS_DIR = Path(__file__).parent / "prompts"
ROUTER_PROMPT_PATH = PROMPTS_DIR / "router_v2.md"

# LLM fallback 설정
TEMPERATURE_ROUTER = 0.0  # 라우팅은 결정적 — 가장 낮게
MAX_TOKENS_ROUTER = 150   # route + reasoning 1줄이면 충분


# ── 결과 객체 ────────────────────────────────────────────────
@dataclass
class RouteDecision:
    """라우팅 결정 결과.

    어떤 라우트로 가는지 + 왜 그렇게 결정했는지의 trace.
    """

    route: Route
    matched_keywords: list[str] = field(default_factory=list)
    llm_used: bool = False  # LLM fallback 사용 여부
    llm_reasoning: str = ""  # LLM fallback 시 이유 (사용 안 했으면 "")
    error: str | None = None  # LLM 호출 실패 시 메시지 (그래도 default 로 진행)


@dataclass
class RoutedResult:
    """라우팅된 retriever 의 답변 + 라우팅 메타데이터.

    weekly-log 박제 / Opik trace / R1~R3 평가 셋 모두 본 객체 활용.
    """

    question: str
    decision: RouteDecision
    answer: str
    # 어느 retriever 가 실행됐는지에 따라 셋 중 하나만 채워짐
    t2c_result: Text2CypherResult | None = None
    local_result: LocalRetrieverResult | None = None
    community_result: CommunitySummaryResult | None = None
    elapsed_seconds: float = 0.0


# ── 1단계: 키워드 분기 ───────────────────────────────────────
def _classify_by_keywords(question: str) -> RouteDecision:
    """질문 → 키워드 기반 라우트 결정.

    Local / Community 키워드를 동시에 검사하고:
    - Local 키워드만 매칭 → local
    - Community 키워드만 매칭 → community
    - 둘 다 매칭 → 더 많은 쪽 (동률이면 community 우선 — 전체 질의는 보통 community 의도)
    - 아무것도 매칭 안 됨 → route=None 의미로 빈 RouteDecision (LLM fallback 으로 갈 signal)

    Note: 반환값의 route 가 DEFAULT_ROUTE (= "local", 5/25 v2) 면 두 가지 의미일 수 있음:
    - 매칭된 키워드 있음 + 결과적으로 local 이 더 적합 (지금은 없음)
    - 매칭 0개 → caller 가 matched_keywords 비어 있는지로 LLM fallback 트리거
    """
    q = question.lower() if question else ""
    local_hits = [kw for kw in LOCAL_KEYWORDS if kw.lower() in q]
    community_hits = [kw for kw in COMMUNITY_KEYWORDS if kw.lower() in q]

    # 둘 다 비어 있음 → LLM fallback 신호 (route 는 임시로 default, caller 가 판단)
    if not local_hits and not community_hits:
        return RouteDecision(route=DEFAULT_ROUTE, matched_keywords=[])

    # Local 만
    if local_hits and not community_hits:
        return RouteDecision(route="local", matched_keywords=local_hits)

    # Community 만
    if community_hits and not local_hits:
        return RouteDecision(route="community", matched_keywords=community_hits)

    # 둘 다 — 더 많은 쪽 (tie 시 community)
    if len(community_hits) >= len(local_hits):
        return RouteDecision(
            route="community",
            matched_keywords=community_hits + local_hits,
        )
    return RouteDecision(
        route="local",
        matched_keywords=local_hits + community_hits,
    )


# ── 2단계: LLM fallback ─────────────────────────────────────
_CODEFENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_codefence(raw: str) -> str:
    raw = raw.strip()
    m = _CODEFENCE_RE.match(raw)
    return m.group(1).strip() if m else raw


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=5),  # router 는 짧게 — 어차피 default 있음
    stop=stop_after_attempt(2),
    reraise=True,
)
def _call_llm_router(
    llm: LLMClient, system_prompt: str, user_prompt: str
) -> str:
    """LLM 호출 — JSON 응답 강제. 짧은 응답이라 max_tokens 작게."""
    return llm.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=TEMPERATURE_ROUTER,
        max_tokens=MAX_TOKENS_ROUTER,
        response_format={"type": "json_object"},
    )


def _classify_by_llm(
    llm: LLMClient, question: str, system_prompt: str
) -> RouteDecision:
    """LLM 으로 라우팅 결정. 실패하면 default (local, 5/25 v2) 로 fallback.

    LLM 응답 예상 형식:
      {"route": "t2c" | "local" | "community", "reasoning": "..."}
    """
    user_prompt = f"질문: {question}"
    try:
        raw = _call_llm_router(llm, system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("LLM router 호출 실패: %s — default(%s) 로 진행",
                       exc, DEFAULT_ROUTE)
        return RouteDecision(
            route=DEFAULT_ROUTE,
            llm_used=True,
            llm_reasoning="",
            error=f"LLM 호출 실패: {exc}",
        )

    try:
        data = json.loads(_strip_codefence(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("LLM router 응답 JSON 파싱 실패: %s | raw=%r",
                       exc, raw[:200])
        return RouteDecision(
            route=DEFAULT_ROUTE,
            llm_used=True,
            llm_reasoning="",
            error=f"JSON 파싱 실패: {exc}",
        )

    route = (data.get("route") or "").strip().lower()
    reasoning = (data.get("reasoning") or "").strip()

    if route not in ("t2c", "local", "community"):
        logger.warning("LLM router 가 알 수 없는 route 반환: %r — default(%s)",
                       route, DEFAULT_ROUTE)
        return RouteDecision(
            route=DEFAULT_ROUTE,
            llm_used=True,
            llm_reasoning=reasoning,
            error=f"unknown route: {route!r}",
        )

    return RouteDecision(
        route=route,  # type: ignore[arg-type]
        llm_used=True,
        llm_reasoning=reasoning,
    )


# ── 통합 라우팅 ──────────────────────────────────────────────
def decide_route(
    question: str,
    llm: LLMClient | None = None,
) -> RouteDecision:
    """질문 → RouteDecision (라우팅 결정만, retriever 호출은 X).

    1단계 키워드 분기 → 매칭 0개면 2단계 LLM fallback. LLM 실패 시 default(local, 5/25 v2).

    Args:
        question: 사용자 자연어 질문.
        llm: LLMClient (테스트용 mock 주입 가능). LLM fallback 단계에서만 사용.

    Returns:
        RouteDecision — 어느 retriever 로 갈지 + trace.
    """
    if not question or not question.strip():
        return RouteDecision(route=DEFAULT_ROUTE, matched_keywords=[])

    # 1단계: 키워드
    decision = _classify_by_keywords(question)
    if decision.matched_keywords:
        logger.info(
            "Routing 키워드 분기 → %s (matched: %s)",
            decision.route, decision.matched_keywords,
        )
        return decision

    # 2단계: LLM fallback
    logger.info("Routing 키워드 매칭 0개 — LLM fallback 진입")
    llm = llm or LLMClient()
    system_prompt = _load_prompt(ROUTER_PROMPT_PATH)
    decision = _classify_by_llm(llm, question, system_prompt)
    logger.info(
        "Routing LLM 분기 → %s (reasoning=%r, error=%r)",
        decision.route, decision.llm_reasoning[:80], decision.error,
    )
    return decision


@track
def route_and_answer(
    question: str,
    llm: LLMClient | None = None,
    neo4j: Neo4jClient | None = None,
) -> RoutedResult:
    """자연어 질문 → 라우팅 → 해당 retriever 호출 → 통합 답변.

    DoD (#21):
    - 키워드 기반 분기 (관계 → local, 트렌드 → community, 기타 → local) ✅
    - LLM fallback (키워드 매칭 0개 시) ✅
    - graceful default — LLM 실패 시 local (5/25 v2) ✅
    - 통합 진입점으로 발표 슬라이드 14 데모 가능 ✅

    Args:
        question: 사용자 자연어 질문.
        llm: LLMClient (테스트용 mock 주입 가능). 라우팅 + 하위 retriever 양쪽에 전달.
        neo4j: Neo4jClient (테스트용 mock 주입 가능). t2c / local 에 전달.

    Returns:
        RoutedResult — 라우팅 결정 + 해당 retriever 결과 + 통합 answer.
    """
    started = time.perf_counter()
    if not question or not question.strip():
        return RoutedResult(
            question=question,
            decision=RouteDecision(route=DEFAULT_ROUTE),
            answer="질문이 비어 있습니다. 그래프에 대해 궁금한 점을 입력해 주세요.",
            elapsed_seconds=time.perf_counter() - started,
        )

    # LLMClient / Neo4jClient 공유 — 테스트 시 mock 주입 + 라우팅에 쓴 LLM 그대로
    # 하위 retriever 에 전달하여 호출 1회를 양쪽에서 활용 가능 (현재는 라우팅이 따로
    # LLM 호출하므로 공유 효과는 없지만 시그니처는 일관성 유지).
    own_neo4j = neo4j is None
    neo4j = neo4j or Neo4jClient()
    own_llm = llm is None
    llm = llm or LLMClient()

    try:
        # 1) 라우팅 결정
        decision = decide_route(question, llm=llm)
        logger.info(
            "Routing 결과 → %s (llm_used=%s, matched=%s)",
            decision.route, decision.llm_used, decision.matched_keywords,
        )

        # 2) 결정된 retriever 호출
        if decision.route == "t2c":
            t2c_res = text2cypher(question, llm=llm, neo4j=neo4j)
            answer = t2c_res.answer
            elapsed = time.perf_counter() - started
            return RoutedResult(
                question=question,
                decision=decision,
                answer=answer,
                t2c_result=t2c_res,
                elapsed_seconds=elapsed,
            )
        if decision.route == "local":
            local_res = local_retrieve(question, llm=llm, neo4j=neo4j)
            answer = local_res.answer
            elapsed = time.perf_counter() - started
            return RoutedResult(
                question=question,
                decision=decision,
                answer=answer,
                local_result=local_res,
                elapsed_seconds=elapsed,
            )
        if decision.route == "community":
            community_res = community_summary(question)
            answer = community_res.answer
            elapsed = time.perf_counter() - started
            return RoutedResult(
                question=question,
                decision=decision,
                answer=answer,
                community_result=community_res,
                elapsed_seconds=elapsed,
            )

        # 도달 불가 (Route literal 검증으로 막힘) — 안전망
        raise ValueError(f"unknown route: {decision.route!r}")

    finally:
        if own_neo4j:
            neo4j.close()
        # llm 은 close 필요 없음 (LLMClient 는 stateless wrapper)
