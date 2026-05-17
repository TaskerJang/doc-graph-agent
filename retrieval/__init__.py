"""Retrieval 모듈 — 자연어 질의 → 그래프 검색 → 자연어 답변.

W4 retrieval 진입점들:
- Layer A (Text2Cypher, #18) — 자연어 → Cypher → 결과 → 자연어. factual / topN 강함.
- Layer B (Local Retriever, #19) — entity 식별 → 1-hop subgraph traversal. 관계 질의 강함.
- Layer C (Community Summary, #20, stub) — community / topic 기반 글로벌 요약. W5+ 실제 구현.
- Routing Agent (#21) — 질문 유형에 따라 Layer A/B/C 분기 (키워드 + LLM fallback).

진입점 권장:
- `route_and_answer(question)` — Routing Agent 통합 진입점 (#21). 일반 사용.
- 개별 retriever 함수도 그대로 export — 명시적 테스트 / 직접 호출 시 사용.
"""

from retrieval.community_summary import (
    CommunitySummaryResult,
    community_summary,
)
from retrieval.local_retriever import (
    LocalRetrieverError,
    LocalRetrieverResult,
    local_retrieve,
)
from retrieval.router import (
    DEFAULT_ROUTE,
    Route,
    RouteDecision,
    RoutedResult,
    decide_route,
    route_and_answer,
)
from retrieval.text2cypher import (
    Text2CypherError,
    Text2CypherResult,
    text2cypher,
)

__all__ = [
    # Routing (#21) — 권장 진입점
    "DEFAULT_ROUTE",
    "Route",
    "RouteDecision",
    "RoutedResult",
    "decide_route",
    "route_and_answer",
    # Text2Cypher (#18)
    "Text2CypherError",
    "Text2CypherResult",
    "text2cypher",
    # Local Retriever (#19)
    "LocalRetrieverError",
    "LocalRetrieverResult",
    "local_retrieve",
    # Community Summary (#20, stub)
    "CommunitySummaryResult",
    "community_summary",
]
