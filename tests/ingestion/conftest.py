"""
인제스트 통합 테스트용 fixture.

평가 셋 8문서는 회사 레포 자산이라 본 레포에 commit하지 않는다.
환경변수 `DOC_FIXTURE_DIR`로 절대 경로를 지정해야 통합 테스트 실행됨.

사용법 (Windows cmd):
    set DOC_FIXTURE_DIR=C:\\path\\to\\doc-summary-agent\\eval\\dataset\\documents
    pytest tests/ingestion -v

사용법 (Linux/macOS):
    export DOC_FIXTURE_DIR=/path/to/doc-summary-agent/eval/dataset/documents
    pytest tests/ingestion -v

환경변수 없으면 fixture를 사용하는 테스트는 자동 skip된다.
단위 테스트(test_chunker, test_adapter의 mock 입력)는 항상 실행.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# 평가 셋 8문서의 파일명 (qa_pairs.json의 doc 필드와 일치)
EVAL_DOCS: list[str] = [
    "한화투자증권_두산밥캣_기업분석_리포트.pdf",
    "DS투자증권_시황분석_리포트.pdf",
    "미래에셋증권_1분기_실적보고서.pdf",
    "미래에셋증권_2분기_실적보고서.pdf",
    "미래에셋증권_3분기_실적보고서.pdf",
    "미래에셋증권_4분기_실적보고서.pdf",
    "농협_2022년_9월말_기준_사업보고서.hwp",
    "금융감독원_251125__보도자료__25_10월중_기업의_직접금융_조달실적.docx",
]


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    """
    평가 셋 문서 디렉토리 (환경변수 DOC_FIXTURE_DIR).

    환경변수가 없거나 디렉토리가 존재하지 않으면 테스트를 skip 처리한다.
    """
    raw = os.environ.get("DOC_FIXTURE_DIR")
    if not raw:
        pytest.skip("DOC_FIXTURE_DIR 미설정 — 통합 테스트 skip")

    p = Path(raw)
    if not p.is_dir():
        pytest.skip(f"DOC_FIXTURE_DIR이 디렉토리가 아님: {p}")

    return p


@pytest.fixture(scope="session")
def eval_doc_paths(fixture_dir: Path) -> list[Path]:
    """평가 셋 8문서의 절대 경로. 누락된 파일은 fail."""
    paths = [fixture_dir / name for name in EVAL_DOCS]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        pytest.skip(f"평가 셋 문서 누락 — DOC_FIXTURE_DIR 확인: {missing}")
    return paths
