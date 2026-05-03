"""
adapter.py 단위 테스트.

mock chunker 출력 → Layer A 객체 변환 검증.
DOC_FIXTURE_DIR과 무관하게 항상 실행.
"""
from __future__ import annotations

from ingestion import adapter
from ingestion.models import (
    ChunkType,
    DocType,
    SourceFormat,
)


# ── _detect_source_format ─────────────────────────────────────


def test_detect_source_format():
    from pathlib import Path

    assert adapter._detect_source_format(Path("foo.pdf")) == SourceFormat.PDF
    assert adapter._detect_source_format(Path("foo.docx")) == SourceFormat.DOCX
    assert adapter._detect_source_format(Path("foo.HWP")) == SourceFormat.HWP


def test_detect_source_format_unsupported():
    from pathlib import Path
    import pytest

    with pytest.raises(ValueError, match="지원하지 않는 포맷"):
        adapter._detect_source_format(Path("foo.txt"))


# ── _infer_doc_type ────────────────────────────────────────────


def test_infer_doc_type_filing():
    """사업보고서 → filing."""
    assert adapter._infer_doc_type("농협_2022년_9월말_기준_사업보고서.hwp") == DocType.FILING


def test_infer_doc_type_ir():
    """분기 실적보고서 → ir."""
    assert adapter._infer_doc_type("미래에셋증권_4분기_실적보고서.pdf") == DocType.IR


def test_infer_doc_type_disclosure():
    """금감원 보도자료 → disclosure."""
    assert adapter._infer_doc_type(
        "금융감독원_251125__보도자료__25_10월중_기업의_직접금융_조달실적.docx"
    ) == DocType.DISCLOSURE


def test_infer_doc_type_report_default():
    """증권사 리포트 → report (기본값)."""
    assert adapter._infer_doc_type("한화투자증권_두산밥캣_기업분석_리포트.pdf") == DocType.REPORT
    assert adapter._infer_doc_type("DS투자증권_시황분석_리포트.pdf") == DocType.REPORT


# ── _heading_level ─────────────────────────────────────────────


def test_heading_level():
    assert adapter._heading_level("# 제목") == 1
    assert adapter._heading_level("## 부제목") == 2
    assert adapter._heading_level("### 소제목") == 3
    assert adapter._heading_level("####### 너무 깊음") == 3  # 최대 3
    assert adapter._heading_level("일반 텍스트") == 1
    assert adapter._heading_level("") == 1


# ── chunks_to_layer_a ───────────────────────────────────────────


def _mock_chunk(
    section: str,
    text: str,
    chunk_type: str = "text",
    chunk_index: int = 0,
    doc_year: str | None = None,
    section_type: str | None = None,
    metrics: list[str] | None = None,
):
    """chunker.Chunk(TypedDict)와 동일 구조의 dict."""
    return {
        "section": section,
        "page": None,
        "chunk_index": chunk_index,
        "text": text,
        "chunk_type": chunk_type,
        "doc_year": doc_year,
        "section_type": section_type,
        "metrics": metrics or [],
    }


def test_chunks_to_layer_a_groups_by_section():
    """동일 section의 청크는 같은 Section 노드에 그룹핑."""
    flat = [
        _mock_chunk("# 섹션 A", "본문 A1", chunk_index=0),
        _mock_chunk("# 섹션 A", "본문 A2", chunk_index=1),
        _mock_chunk("# 섹션 B", "본문 B1", chunk_index=2),
    ]
    sections = adapter.chunks_to_layer_a(flat, doc_id="doc1", doc_type=DocType.REPORT)

    assert len(sections) == 2
    assert sections[0].original_section == "# 섹션 A"
    assert sections[1].original_section == "# 섹션 B"
    assert len(sections[0].chunks) == 2
    assert len(sections[1].chunks) == 1


def test_chunks_to_layer_a_table_separated():
    """chunk_type='table'은 Section.tables로, 'text'는 Section.chunks로."""
    flat = [
        _mock_chunk("# 섹션", "텍스트 본문", chunk_type="text", chunk_index=0),
        _mock_chunk("# 섹션", "| a | b |\n|---|---|\n| 1 | 2 |", chunk_type="table", chunk_index=1),
    ]
    sections = adapter.chunks_to_layer_a(flat, doc_id="doc1", doc_type=DocType.IR)

    assert len(sections) == 1
    section = sections[0]
    assert len(section.chunks) == 1
    assert len(section.tables) == 1
    assert section.chunks[0].chunk_type == ChunkType.TEXT
    assert section.tables[0].raw_markdown.startswith("| a |")


def test_chunks_to_layer_a_empty_section_label():
    """빈 section 문자열 → '(no-heading)' 라벨로 그룹핑."""
    flat = [
        _mock_chunk("", "헤딩 없는 본문 1", chunk_index=0),
        _mock_chunk("", "헤딩 없는 본문 2", chunk_index=1),
    ]
    sections = adapter.chunks_to_layer_a(flat, doc_id="doc1", doc_type=DocType.REPORT)

    assert len(sections) == 1
    assert sections[0].original_section == "(no-heading)"


def test_chunks_to_layer_a_metadata_propagated():
    """chunker의 doc_year/section_type/metrics가 Chunk 객체에 그대로 전달."""
    flat = [
        _mock_chunk(
            "# 2023 실적",
            "2023년 영업이익은 ROE 12% 기록.",
            doc_year="2023",
            section_type="실적",
            metrics=["영업이익", "ROE"],
        ),
    ]
    sections = adapter.chunks_to_layer_a(flat, doc_id="doc1", doc_type=DocType.REPORT)

    chunk = sections[0].chunks[0]
    assert chunk.doc_year == "2023"
    assert chunk.section_type_hint == "실적"
    assert chunk.metric_keywords == ["영업이익", "ROE"]


def test_chunks_to_layer_a_ids_unique():
    """생성된 Section/Chunk/Table ID가 모두 unique."""
    flat = [
        _mock_chunk("# A", "본문 1", chunk_index=0),
        _mock_chunk("# A", "본문 2", chunk_index=1),
        _mock_chunk("# B", "| h |", chunk_type="table", chunk_index=2),
    ]
    sections = adapter.chunks_to_layer_a(flat, doc_id="doc1", doc_type=DocType.REPORT)

    section_ids = [s.id for s in sections]
    chunk_ids = [c.id for s in sections for c in s.chunks]
    table_ids = [t.id for s in sections for t in s.tables]

    assert len(section_ids) == len(set(section_ids))
    assert len(chunk_ids) == len(set(chunk_ids))
    assert len(table_ids) == len(set(table_ids))


def test_chunks_to_layer_a_section_label_is_none():
    """W3 LLM 추출 전이라 SectionLabel은 None."""
    flat = [_mock_chunk("# 섹션", "본문")]
    sections = adapter.chunks_to_layer_a(flat, doc_id="doc1", doc_type=DocType.REPORT)
    assert sections[0].label is None


def test_chunks_to_layer_a_doc_type_propagated():
    """Section.doc_type이 인자로 받은 doc_type과 일치."""
    flat = [_mock_chunk("# 섹션", "본문")]
    sections = adapter.chunks_to_layer_a(flat, doc_id="doc1", doc_type=DocType.IR)
    assert sections[0].doc_type == DocType.IR


def test_chunks_to_layer_a_empty_input():
    """빈 입력 → 빈 리스트."""
    sections = adapter.chunks_to_layer_a([], doc_id="doc1", doc_type=DocType.REPORT)
    assert sections == []
