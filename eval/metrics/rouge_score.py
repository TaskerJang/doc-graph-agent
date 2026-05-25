"""
eval/metrics/rouge_score.py
ROUGE-1 / ROUGE-2 / ROUGE-L 계산 (doc-summary-agent 와 동일)

한국어 형태소 토크나이저: python-mecab-ko
설치: uv add python-mecab-ko rouge-score
"""
import logging

from rouge_score import rouge_scorer
from mecab import MeCab

logger = logging.getLogger(__name__)

_mecab = MeCab()


class _MeCabTokenizer:
    """rouge_score 라이브러리 호환 한국어 MeCab 토크나이저."""

    def tokenize(self, text: str) -> list[str]:
        return [token.surface for token in _mecab.parse(text)]


_SCORER = rouge_scorer.RougeScorer(
    ['rouge1', 'rouge2', 'rougeL'],
    use_stemmer=False,
    tokenizer=_MeCabTokenizer(),
)

_EMPTY: dict = {'rouge1': 0.0, 'rouge2': 0.0, 'rougeL': 0.0}


def compute_rouge(prediction: str, reference: str) -> dict:
    if not prediction or not reference:
        logger.warning("compute_rouge: 빈 입력, 0.0 반환")
        return _EMPTY.copy()

    scores = _SCORER.score(reference, prediction)
    return {
        'rouge1': round(scores['rouge1'].fmeasure, 4),
        'rouge2': round(scores['rouge2'].fmeasure, 4),
        'rougeL': round(scores['rougeL'].fmeasure, 4),
    }
