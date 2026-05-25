"""eval/metrics/semantic_similarity.py
RAGAS Answer Semantic Similarity — 임베딩 cosine similarity.

## 원천
- RAGAS Answer Semantic Similarity (https://docs.ragas.io)
  : 정답과 예측의 임베딩 벡터 cosine 유사도

## ROUGE-L 와 차이
- ROUGE-L: 특정 토큰 일치 기반 → "두산밥칿 목표주가 80,000원" vs "목표가격은 8만원" → 낮은 점수
- Semantic Similarity: 의미 기반 → 같은 두 문장 → 높은 유사도 (~0.85)

## 실제 구현
- sentence-transformers 의 BAAI/bge-m3 사용 — 다국어 고성능
- doc-summary-agent 와 동일사용 (이미 캐싱됨)
- 하지만 doc-graph-agent 에서도 사용해야 해서 동일 의존성 필요:
  uv add sentence-transformers

## 사용
from eval.metrics.semantic_similarity import compute_semantic_similarity

sim = compute_semantic_similarity(
    prediction="두산밥칿의 목표주가는 80,000원입니다.",
    reference="80,000원",
)
# {"semantic_similarity": 0.7234}

## 메모리 주의
- bge-m3 로딩이 ~2GB. 식단의 경우 처음 사용 시 다운로드 필요.
- CPU 에서 처음 임베딩은 느림. dry-run 시 5개 QA 먼저 테스트.
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)

_encoder = None


def _get_encoder():
    """sentence-transformers bge-m3 로더 — lazy 로딩."""
    global _encoder
    if _encoder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _encoder = SentenceTransformer("BAAI/bge-m3")
            logger.info("semantic_similarity: bge-m3 로딩 완료")
        except ImportError as e:
            logger.error(
                "sentence-transformers 미설치 — 'uv add sentence-transformers' 필요: %s", e,
            )
            raise
    return _encoder


def compute_semantic_similarity(prediction: str, reference: str) -> dict:
    """임베딩 cosine 유사도 계산.

    Returns:
        {"semantic_similarity": float 0~1}
        실패 시 {"semantic_similarity": None, "error": str}
    """
    if not prediction or not reference:
        return {"semantic_similarity": 0.0}

    try:
        encoder = _get_encoder()
        embs = encoder.encode([prediction, reference], normalize_embeddings=True, show_progress_bar=False)
        sim = float(np.dot(embs[0], embs[1]))
        # cosine 은 [-1, 1] 이나 정규화된 벡터는 실질적으로 [0, 1].
        sim = max(0.0, min(1.0, sim))
        return {"semantic_similarity": round(sim, 4)}
    except Exception as e:
        logger.error("semantic_similarity 계산 실패: %s", e)
        return {"semantic_similarity": None, "error": str(e)}
