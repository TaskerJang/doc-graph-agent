"""
chunker.py 단위 테스트 + 통합 sanity check.

단위 테스트(unit):
- mock markdown 입력 → chunk 수, chunk_type, 메타데이터 검증
- 환경변수 무관, 항상 실행

통합 sanity check(integration):
- 실제 평가 셋 8문서 → chunk 수가 예상 범위인지 확인
- DOC_FIXTURE_DIR 환경변수 설정 시에만 실행 (conftest.py 참고)
- 회사 레포 동일 정책(700/200/50)이라 chunk 수 자체는 회사 레포와 동일해야 함
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ingestion import chunker


# ── 단위 테스트 ─────────────────────────────────────────────────────


def test_chunk_empty_input():
    """빈 텍스트 → 빈 리스트."""
    assert chunker.chunk("") == []
    assert chunker.chunk("   \n\n  ") == []


def test_chunk_below_min_size_skipped():
    """min_chunk_size 미만이면 청크 생성되지 않음."""
    short = "짧은 텍스트"  # 7자 — DEFAULT_MIN_CHUNK_SIZE=50 미만
    chunks = chunker.chunk(short)
    assert chunks == []


def test_chunk_simple_text():
    """heading 없는 단일 단락 → 1청크."""
    text = "이것은 테스트 문장입니다. " * 10  # 약 130자
    chunks = chunker.chunk(text)
    assert len(chunks) == 1
    assert chunks[0]["chunk_type"] == "text"
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["section"] == ""


def test_chunk_with_headings():
    """heading 기반 섹션 분리.

    ⚠️ 함정 주의: Python의 인접 리터럴 결합과 * 연산자 우선순위 때문에
        "# 제목\n\n" "본문 " * 10  → "# 제목\n\n본문 " * 10  으로 쇄제됨.
        이러면 제목이 본문 안에 10번 반복되어 박혀 의도와 다르게 파싱됨.
        명시적 변수 분리로 결합해야 안전함.
    """
    section1_body = "첫 섹션 본문입니다. " * 10
    section2_body = "두 번째 본문입니다. " * 10
    text = (
        "# 첫 섹션\n\n"
        + section1_body
        + "\n\n# 두 번째 섹션\n\n"
        + section2_body
    )
    chunks = chunker.chunk(text)

    sections = {c["section"] for c in chunks}
    assert "# 첫 섹션" in sections
    assert "# 두 번째 섹션" in sections
    assert len(chunks) >= 2


def test_chunk_skip_section_disclaimer():
    """면책 키워드가 있는 섹션은 제외.

    주의: test_chunk_with_headings와 같은 인접 리터럴 결합 함정 회피.
    """
    body1 = "정상 본문입니다. " * 10
    body2 = "compliance 면책 조항입니다. " * 10
    text = (
        "# 본문 섹션\n\n"
        + body1
        + "\n\n# Compliance 고지\n\n"
        + body2
    )
    chunks = chunker.chunk(text)
    sections = {c["section"] for c in chunks}
    assert "# 본문 섹션" in sections
    assert not any("compliance" in s.lower() for s in sections)


def test_chunk_table_block_detected():
    """표 형식 텍스트는 chunk_type=table로 분류."""
    text = (
        "# 표 섹션\n\n"
        "| 항목 | 값 |\n"
        "|---|---|\n"
        "| 매출 | 1000 |\n"
        "| 영업이익 | 200 |\n"
        "| 순이익 | 150 |\n"
        "| ROE | 12.4% |\n"
        "| ROA | 5.2% |\n"
    )
    chunks = chunker.chunk(text)
    table_chunks = [c for c in chunks if c["chunk_type"] == "table"]
    assert len(table_chunks) >= 1


def test_chunk_metadata_fields_populated():
    """청크 메타데이터(doc_year, section_type, metrics) 추출 검증."""
    text = (
        "# 2023년 실적 분석\n\n"
        "2023년 영업이익은 전년 대비 증가했습니다. ROE는 12.4%를 기록했습니다. " * 5
    )
    chunks = chunker.chunk(text)
    assert len(chunks) >= 1

    c = chunks[0]
    assert c["doc_year"] == "2023"
    assert c["section_type"] == "실적"
    assert "영업이익" in c["metrics"]
    assert "ROE" in c["metrics"]


def test_chunk_size_default_constants():
    """회사 레포 동일성 — chunk_size/overlap/min 기본값 박제."""
    assert chunker.DEFAULT_CHUNK_SIZE == 700
    assert chunker.DEFAULT_CHUNK_OVERLAP == 200
    assert chunker.DEFAULT_MIN_CHUNK_SIZE == 50


def test_chunk_indices_sequential():
    """chunk_index는 0부터 순차적으로 부여."""
    text = (
        "# 섹션 1\n\n"
        + ("긴 본문입니다. " * 200)  # 청크 분할 강제
        + "\n\n# 섹션 2\n\n"
        + ("또 다른 본문입니다. " * 200)
    )
    chunks = chunker.chunk(text)
    indices = [c["chunk_index"] for c in chunks]
    assert indices == list(range(len(chunks)))


# ── 통합 sanity check ─────────────────────────────────────────


def test_eval_docs_chunk_count_sane(eval_doc_paths: list[Path]):
    """
    평가 셋 8문서를 인제스트해서 chunk 수가 합리적 범위인지 확인.

    기대치:
      - 각 문서 → 최소 1청크 (빈 결과 아님)
      - 각 문서 → 최대 200청크 (chunk_size=700 기준 비현실적 상한)
    """
    pytest.importorskip("ingestion.doc_parser.pdf")  # 의존성 미설치 시 skip

    from ingestion import doc_parser

    counts: dict[str, int] = {}
    for path in eval_doc_paths:
        try:
            md = doc_parser.parse(path)
        except Exception as e:
            pytest.fail(f"파싱 실패 {path.name}: {e}")

        chunks = chunker.chunk(md)
        counts[path.name] = len(chunks)

        assert len(chunks) >= 1, f"{path.name}: 청크 0개"
        assert len(chunks) <= 200, f"{path.name}: 청크 너무 많음 ({len(chunks)})"

    print("\n=== 평가 셋 chunk 수 ===")
    for name, n in counts.items():
        print(f"  {n:3d}  {name}")
