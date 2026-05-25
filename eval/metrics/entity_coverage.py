"""eval/metrics/entity_coverage.py
RAGAS Context Entity Recall 변형 — 정답 entity 가 예측에 등장하는 비율.

## 원천
- RAGAS Context Entities Recall (https://docs.ragas.io)
  : ground_truth 에서 entity 추출 → retrieved_context 에 등장하는 비율

## 변형
- 원본 RAGAS 는 *의존성 추가 (spacy 등)* 때문에 도입 안 함
- 대신 우리 도메인에 맞게 *단순 substring match* 으로 구현:
  - 정답에서 수치 + Company/Risk 명사 수동 추출 (numerical_accuracy 패턴 재사용)
  - QA 의 key_entities 필드 있으면 그것 우선

## 사용
from eval.metrics.entity_coverage import compute_entity_coverage

result = compute_entity_coverage(
    prediction="두산밥칿은 관세, 환율 리스크에 노출",
    reference="관세, 환율, 금리",
    key_entities=["관세", "환율", "금리"],  # 선택
)
# {"entity_coverage": 0.6667, "matched": ["관세", "환율"], "missed": ["금리"], "total": 3}
"""
import logging
import re
from typing import Optional

from eval.metrics.numerical_accuracy import extract_numbers

logger = logging.getLogger(__name__)


def _extract_named_entities(text: str) -> list[str]:
    """정답에서 *명사형 entity* 단순 추출.

    금융 도메인 heuristic:
    - 2~10글자 한글 명사 연속 (Company/Risk/Metric 프록시)
    - 수치/단위 제외 (numerical_accuracy 가 이미 먹음)
    - 조사 없이 단독으로 등장하는 단어 우선
    """
    # 한글 명사 2~10글자 패턴 (조사 제외)
    pattern = re.compile(r'[\uac00-\ud7a3]{2,10}')
    candidates = pattern.findall(text)

    # 조사 / 기능어 필터
    STOPWORDS = {
        "이곳", "저곥", "그곳", "이것", "저것", "그것",
        "한다", "하는", "되는", "있다", "없다",
        "서말", "대비", "대해", "대한", "따릅", "위한",
        "목표", "결과", "수준", "기준",
        "N/A", "문서", "내용", "없음", "없는",
    }
    filtered = [c for c in candidates if c not in STOPWORDS]

    # 중복 제거 (순서 유지)
    seen = set()
    result = []
    for c in filtered:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def compute_entity_coverage(
    prediction: str,
    reference: str,
    key_entities: Optional[list[str]] = None,
) -> dict:
    """정답의 주요 entity (명사 + 수치) 가 예측에 등장하는 비율.

    Args:
        prediction: 모델이 생성한 답변
        reference: 정답 윈텍스트
        key_entities: QA 쟑입 시 논레이손 (graphrag_qa.json 에 필드 있으면 우선 사용)

    Returns:
        {"entity_coverage": 0~1, "matched": [...], "missed": [...], "total": int}
    """
    if not prediction or not reference:
        return {"entity_coverage": 0.0, "matched": [], "missed": [], "total": 0}

    # 1. entity 추출 — key_entities 세 있으면 그것 우선, 없으면 reference 에서 자동 추출
    if key_entities:
        target_entities = list(key_entities)
    else:
        # 수치 + 단순 명사 entity 합치기
        target_entities = list(set(
            extract_numbers(reference) + _extract_named_entities(reference)
        ))

    if not target_entities:
        return {"entity_coverage": 1.0, "matched": [], "missed": [], "total": 0}

    # 2. 예측에 각 entity substring 등장 여부
    matched = []
    missed = []
    for e in target_entities:
        # 수치는 콤마 제거 어서 비교 (numerical_accuracy 과 같이)
        e_norm = e.replace(",", "").replace(" ", "")
        pred_norm = prediction.replace(",", "").replace(" ", "")
        if e_norm in pred_norm or e in prediction:
            matched.append(e)
        else:
            missed.append(e)

    return {
        "entity_coverage": round(len(matched) / len(target_entities), 4),
        "matched": matched,
        "missed": missed,
        "total": len(target_entities),
    }
