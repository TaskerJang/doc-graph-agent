"""eval/metrics/routing_accuracy.py
GraphRAG-Bench AR Metric 변형 — 의도된 route vs 실제 route 일치 여부.

## 원천
- GraphRAG-Bench (arxiv:2506.02404) AR Metric
  : "답변이 정확하면서 *올바른 추론 경로* 를 따랐는지"

## 변형
- 본 연구는 retrieval 경로를 GraphRAG-Bench 처럼 *자연어 rationale* 로 평가하지 않고
  *단순 route 레이블 일치* 로 축소 — t2c / local / community
- doc-graph 의 router.py 가 반환하는 actual_route 를 GraphRAG QA 의
  expected_route 와 비교
- doc-summary 측에는 해당 없음 (routing 구조 없음)

## 사용
from eval.metrics.routing_accuracy import compute_routing_accuracy

result = compute_routing_accuracy(
    expected_route="local",
    actual_route="local",
)
# {"routing_correct": True, "expected": "local", "actual": "local"}
"""
from typing import Optional


def compute_routing_accuracy(
    expected_route: Optional[str],
    actual_route: Optional[str],
) -> dict:
    """의도된 route vs 실제 route 일치.

    Args:
        expected_route: QA 자적됬 의도 경로 (graphrag_qa.json expected_route 필드)
        actual_route: router.py 가 틠열뎀으로 선택한 경로

    Returns:
        {
            "routing_correct": bool | None,  # expected 없으면 None
            "expected": str | None,
            "actual": str | None,
        }
    """
    if expected_route is None:
        # VectorRAG QA 등 routing 의도 없는 경우 — 측정 재업
        return {
            "routing_correct": None,
            "expected": None,
            "actual": actual_route,
        }

    return {
        "routing_correct": expected_route == actual_route,
        "expected": expected_route,
        "actual": actual_route,
    }
