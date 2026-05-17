"""Retrieval 모듈 — 자연어 질의 → 그래프 검색 → 자연어 답변.

W4 retrieval 진입점들:
- Layer A (Text2Cypher, #18) — 자연어 → Cypher → 결과 → 자연어. factual / topN 강함.
- Layer B (Local Retriever, #19) — entity 식별 → 1-hop subgraph traversal. 관계 질의 강함.
- Layer C (Community Summary, #20) — community / topic 기반 글로벌 요약 (stub 예정).
- Routing Agent (#21) — 질문 유형에 따라 Layer A/B/C 분기.
"""

from retrieval.local_retriever import (
    LocalRetrieverError,
    LocalRetrieverResult,
    local_retrieve,
)
from retrieval.text2cypher import (
    Text2CypherError,
    Text2CypherResult,
    text2cypher,
)

__all__ = [
    "LocalRetrieverError",
    "LocalRetrieverResult",
    "Text2CypherError",
    "Text2CypherResult",
    "local_retrieve",
    "text2cypher",
]
