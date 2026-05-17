"""Community Summary — Layer C stub (#20).

W4 세 번째 retrieval — Layer C (Community / Topic-level Summarization) 의
**stub** 구현. 실제 community detection (Leiden / Louvain) 과 community 요약은
W5+ 영역. 본 모듈은 Routing Agent (#21) 가 글로벌 질의를 Layer C 로 분기했을 때
**정직한 안내 응답** 을 반환하는 것이 유일한 책임.

왜 stub 만 만드나:
- Microsoft GraphRAG 의 Global Search 는 *indexing time* 에 미리 생성된 community
  summary 위에서 동작. 본 프로젝트는 5/17 기준 community detection 자체가 아직
  미구현 — community 자료가 없는 상태에서 LLM 만 가지고 "글로벌 답변" 을 흉내내는
  것은 정직하지 않은 패턴 (community 구조 없이 흉내 → 거짓말).
- Routing Agent (#21) 가 "이 질문은 Layer C 적합" 이라고 분기하는 동작 자체를
  *시연*하기 위해서는 Layer C 의 진입점 함수가 있어야 함. 본 모듈이 그 진입점.

흐름:
  자연어 질문
     ↓ community_summary
  CommunitySummaryResult (
    answer="Layer C 미구현 안내 + 5/24+ 작업 영역 명시",
    is_stub=True,
  )

text2cypher / local_retriever 와의 차이:
- text2cypher / local_retriever: LLM 호출 + Neo4j 조회 → 실제 답변.
- community_summary (stub): LLM/Neo4j 호출 **없음**. 결정적 응답.

향후 (W5+) 진짜 구현 시 인터페이스:
- 동일한 `community_summary(question) -> CommunitySummaryResult` 시그니처 유지
- `is_stub=False` 로 전환, `community_count`, `top_topics` 등 필드 추가 가능

#24 Opik:
- `@track` 으로 stub 호출도 trace (Routing 분기 검증용).

Reference:
- Microsoft GraphRAG Global Search — community report 기반 map-reduce 패턴.
- Sotaaz blog (2026-01) — "if is_global_question(query): return graphrag.global_search(query)"
  패턴. Layer C 진입점이 분리되어 있어야 라우팅 가능.
- graphrag.com /reference/global-community-summary-retriever — community summary
  retriever 는 *전제 조건* 으로 indexing time community summary 필요.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from observability.tracing import track

logger = logging.getLogger(__name__)


# ── 프롬프트 경로 (참고용 — stub 은 파일 본문 사용 안 함) ────
PROMPTS_DIR = Path(__file__).parent / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "community_summary_v1.md"


# ── 결과 객체 ────────────────────────────────────────────────
@dataclass
class CommunitySummaryResult:
    """Community Summary 한 회차의 결과.

    stub 단계에서는 answer 와 is_stub 만 의미 있음. W5+ 진짜 구현 시 community
    count / top topics / community level 등 추가 예정.

    Opik / weekly-log 박제 시 LocalRetrieverResult / Text2CypherResult 와
    동일한 톤을 유지하기 위해 question / elapsed_seconds / error 필드 포함.
    """

    question: str
    answer: str
    is_stub: bool = True
    elapsed_seconds: float = 0.0
    error: str | None = None


# ── stub 응답 본문 ──────────────────────────────────────────
# 발표 슬라이드 14 (#21 Routing 명분) 의 데모 자료가 됨.
# - 글로벌 질의가 Layer C 로 분기됐다는 사실
# - 현재 미구현 상태 솔직 안내
# - 5/24+ 작업 영역 명시 (실제 구현 ETA)
# - 우회 안내 (특정 entity 로 질문 재구성 시 Local Retriever 활용 가능)
_STUB_ANSWER_TEMPLATE = """질문하신 내용은 전체 문서 corpus 의 트렌드/패턴/요약을 요구하는 **글로벌 질의** 로 판단됩니다.

Layer C (Community Summary) 는 그래프 전체에서 entity 군집 (community) 을 탐지하고 각 군집의 요약을 사전 생성한 뒤, 글로벌 질의에 대해 map-reduce 방식으로 답변을 합성하는 모듈입니다. 본 프로젝트의 Layer C 는 현재 **미구현 (stub)** 상태이며, 5/24+ W5/W6 영역에서 다음 순서로 구현 예정입니다:

1. Community detection (Leiden 알고리즘) — entity 노드 기반 군집 추출
2. Community summary 사전 생성 — 각 군집의 entity / 관계 / 핵심 chunk 요약
3. Global search — 질의 → community summary 위에서 map-reduce 합성

대안 안내:
- 특정 entity (회사명, metric 등) 를 명시한 질문으로 재구성하시면 Layer B (Local Retriever) 로 답변 가능합니다. 예: "두산밥캣과 한화의 관계는?"
- 특정 사실 (개수, top-N, 필터) 을 묻는 질문은 Layer A (Text2Cypher) 가 처리합니다. 예: "보도자료 문서의 entity 개수는?"

원 질문: {question}
"""


# ── 공개 인터페이스 ──────────────────────────────────────────
@track
def community_summary(question: str) -> CommunitySummaryResult:
    """글로벌 질의 → Layer C stub 안내 응답.

    DoD (#20):
    - Routing Agent (#21) 가 글로벌 질의를 분기할 진입점 함수 제공 ✅
    - 정직한 미구현 안내 (가짜 답변 X) ✅
    - LLM / Neo4j 호출 없음 → 즉시 응답 ✅

    Args:
        question: 사용자 자연어 질문.

    Returns:
        CommunitySummaryResult — answer 항상 채워짐. is_stub=True.
    """
    started = time.perf_counter()
    logger.info("CommunitySummary (stub) 시작 — question=%r", question)

    if not question or not question.strip():
        elapsed = time.perf_counter() - started
        return CommunitySummaryResult(
            question=question,
            answer="질문이 비어 있습니다. 그래프에 대해 궁금한 점을 입력해 주세요.",
            is_stub=True,
            elapsed_seconds=elapsed,
        )

    answer = _STUB_ANSWER_TEMPLATE.format(question=question).strip()
    elapsed = time.perf_counter() - started
    logger.info("CommunitySummary (stub) 완료 — elapsed=%.3fs", elapsed)

    return CommunitySummaryResult(
        question=question,
        answer=answer,
        is_stub=True,
        elapsed_seconds=elapsed,
    )
