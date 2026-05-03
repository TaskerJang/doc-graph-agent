# Ported from doc-summary-agent/doc_parser/__init__.py (#11).
# Source: TaskerJang/doc-summary-agent@dev as of 2026-05-03.
# 변경: import path를 ingestion.doc_parser.* 로 조정.
from pathlib import Path

from ingestion.doc_parser import docx, hwp, pdf

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".hwp", ".hwpx"}


def parse(path: Path) -> str:
    """
    진입점 — 확장자 기반으로 파서 라우팅
    지원하지 않는 포맷 입력 시 ValueError 반환
    """
    ext = path.suffix.lower()

    if ext == ".pdf":
        return pdf.parse(path)
    if ext in (".docx", ".doc"):
        return docx.parse(path)
    if ext in (".hwp", ".hwpx"):
        return hwp.parse(path)

    raise ValueError(
        f"지원하지 않는 포맷: '{ext}' | 지원 포맷: {sorted(SUPPORTED_EXTENSIONS)}"
    )
