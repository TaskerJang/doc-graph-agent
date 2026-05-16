"""Retrieval 모듈 — 자연어 질의 → 그래프 검색 → 자연어 답변.

W4 첫 진입점 (#18 Text2Cypher) 부터 시작해서 점진적으로 확장:
- Layer A (Text2Cypher) — 자연어 → Cypher → 결과 → 자연어
- Layer B (Local Retriever) — 특정 entity 중심 그래프 traversal
- Layer C (Community Summary) — 전체 트렌드 질문
- Routing Agent — 질문 유형에 따라 분기 (#21)
"""

from retrieval.text2cypher import (
    Text2CypherResult,
    Text2CypherError,
    text2cypher,
)

__all__ = [
    "Text2CypherResult",
    "Text2CypherError",
    "text2cypher",
]
