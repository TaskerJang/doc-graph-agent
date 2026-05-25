"""
eval/metrics/numerical_accuracy.py
수치 정확도 — 금융 특화 (doc-summary-agent 와 동일)
한국어 단위(억원, 조원, %p, bp, %, 원) 포함 수치 추출 후 일치 여부 확인
"""
import re

_DATE_PATTERN = re.compile(
    r'\d{4}\.\d{1,2}(?:\.\d{1,2})?'
    r'|\d{4}년\s*\d{1,2}월'
    r'|\d{2}/\d{2}'
)

_RANGE_PATTERN = re.compile(
    r'[\+\-]?[\d,]+\.?\d*~[\+\-]?[\d,]+\.?\d*'
    r'(?:\s*(?:조|억|만)?\s*(?:원|달러|엔|위안))?'
    r'(?:\s*[%％](?:p|P)?)?'
    r'(?:\s*bp)?'
    r'(?:\s*개월)?'
)

_NUM_PATTERN = re.compile(
    r'[\+\-]?[\d,]+\.?\d*'
    r'(?:\s*(?:조|억|만)?\s*(?:원|달러|엔|위안))?'
    r'(?:\s*[%％](?:p|P)?)?'
    r'(?:\s*bp)?'
    r'(?:\s*개월)?'
)


def _normalize(token: str) -> str:
    return token.strip().replace(',', '').replace(' ', '')


def extract_numbers(text: str) -> list[str]:
    text = _DATE_PATTERN.sub('', text)
    results = []
    ranges = _RANGE_PATTERN.findall(text)
    for r in ranges:
        n = _normalize(r)
        if n:
            results.append(n)
    text = _RANGE_PATTERN.sub('', text)
    for n in _NUM_PATTERN.findall(text):
        n = _normalize(n)
        if n and n not in ('.', '-', '+'):
            results.append(n)
    seen = set()
    deduped = []
    for n in results:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    return deduped


def compute_numerical_accuracy(prediction: str, reference: str) -> dict:
    ref_nums  = extract_numbers(reference)
    pred_nums = set(extract_numbers(prediction))
    if not ref_nums:
        return {'accuracy': 1.0, 'matched': [], 'missed': [], 'total': 0}
    matched = [n for n in ref_nums if n in pred_nums]
    missed  = [n for n in ref_nums if n not in pred_nums]
    return {
        'accuracy': round(len(matched) / len(ref_nums), 4),
        'matched':  matched,
        'missed':   missed,
        'total':    len(ref_nums),
    }
