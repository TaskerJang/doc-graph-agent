"""
Layer A 어댑터 — 회사 레포 인제스트 결과를 Layer A 객체로 변환.

회사 레포 doc-summary-agent의 인제스트 파이프라인은
    파일 → doc_parser.parse() → str (markdown)
                                  ↓
                          chunker.chunk() → list[Chunk(TypedDict)]
의 평면 list[Chunk] 출력을 사용한다.

본 어댑터는 그 결과를 받아 doc-graph-agent의 Layer A 그래프 객체
(Document → Section → Chunk/Table)로 변환한다.

설계 원칙:
- VectorRAG vs GraphRAG 비교의 정직성을 위해 회사 레포의 chunk 결과는 변형하지 않는다.
- 본 어댑터는 "라벨링·구조화" 변환만 수행하며, 텍스트는 절대 수정하지 않는다.
- Section 라벨(SectionLabel)은 W3 Entity 추출 단계에서 LLM이 채우므로 현재는 None.
- doc_type 추론은 파일명·확장자 기반의 단순 휴리스틱 (W3에서 정교화 예정).
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from ingestion import chunker as _chunker
from ingestion import doc_parser as _doc_parser
from ingestion.models import (
    ChunkType,
    Chunk,
    Document,
    DocType,
    Section,
    SourceFormat,
    Table,
)


# ── 내부 헬퍼 ───────────────────────────────────────────


def _file_hash(path: Path) -> str:
    """파일 SHA-256 앞 16자 — Document.id 후보."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _detect_source_format(path: Path) -> SourceFormat:
    ext = path.suffix.lower().lstrip(".")
    try:
        return SourceFormat(ext)
    except ValueError as e:
        raise ValueError(
            f"지원하지 않는 포맷: '{path.suffix}' | "
            f"지원 포맷: {[f.value for f in SourceFormat]}"
        ) from e


def _infer_doc_type(filename: str) -> DocType:
    """
    파일명 기반 doc_type 휴리스틱 (W3에서 정교화 예정).

    평가 셋 8문서를 정확히 분류하기 위한 최소 규칙:
      - "사업보고서" → filing
      - "실적" / "분기" → ir
      - "감독원" / "보도자료" → disclosure
      - 그 외 → report (증권사 리포트 기본값)
    """
    name = filename.lower()
    if "사업보고서" in filename:
        return DocType.FILING
    if any(kw in filename for kw in ["분기", "실적보고서", "key highlights"]):
        return DocType.IR
    if any(kw in filename for kw in ["감독원", "보도자료"]):
        return DocType.DISCLOSURE
    return DocType.REPORT


def _heading_level(section_title: str) -> int:
    """'### ...' 형태의 마크다운 heading에서 #의 개수를 반환. heading 아니면 1."""
    stripped = section_title.lstrip()
    count = 0
    for ch in stripped:
        if ch == "#":
            count += 1
        else:
            break
    return max(1, min(count, 3))


def _chunk_id(doc_id: str, idx: int) -> str:
    return f"{doc_id}:c{idx:04d}"


def _section_id(doc_id: str, idx: int) -> str:
    return f"{doc_id}:s{idx:03d}"


def _table_id(doc_id: str, idx: int) -> str:
    return f"{doc_id}:t{idx:03d}"


# ── 핵심 어댑터 ────────────────────────────────────────────


def chunks_to_layer_a(
    flat_chunks: list[_chunker.Chunk],
    *,
    doc_id: str,
    doc_type: DocType,
) -> list[Section]:
    """
    회사 레포 chunker가 반환한 list[Chunk(TypedDict)]를
    Layer A의 Section 리스트로 그룹핑한다.

    그룹핑 규칙:
      - 동일한 section 문자열을 가진 청크는 같은 Section으로 묶음
      - section이 빈 문자열인 청크들은 "(no-heading)"이라는 가상 섹션에 배치
      - Section 내 chunk_index 순서 보존
      - chunk_type="table"인 청크는 Section.tables로, "text"는 Section.chunks로

    section_index, chunk_index, table_index는 출현 순서대로 0부터 부여.
    """
    sections_by_title: dict[str, Section] = {}
    section_counter = 0
    chunk_counter = 0
    table_counter = 0

    for raw in flat_chunks:
        title = raw.get("section") or "(no-heading)"

        if title not in sections_by_title:
            sec = Section(
                id=_section_id(doc_id, section_counter),
                original_section=title,
                doc_type=doc_type,
                label=None,  # W3 LLM 추출에서 채움
                heading_level=_heading_level(title),
                order_index=section_counter,
            )
            sections_by_title[title] = sec
            section_counter += 1

        section = sections_by_title[title]

        if raw["chunk_type"] == "table":
            md = raw["text"]
            row_count = sum(1 for line in md.splitlines() if "|" in line)
            # column_count: 첫 표 라인의 | 개수 - 1 (간단 추정)
            first_table_line = next(
                (line for line in md.splitlines() if "|" in line),
                "",
            )
            col_count = max(0, first_table_line.count("|") - 1)

            section.tables.append(Table(
                id=_table_id(doc_id, table_counter),
                raw_markdown=md,
                row_count=row_count,
                column_count=col_count,
                page=raw.get("page"),
                order_index=table_counter,
            ))
            table_counter += 1
        else:
            section.chunks.append(Chunk(
                id=_chunk_id(doc_id, chunk_counter),
                text=raw["text"],
                chunk_type=ChunkType.TEXT,
                char_count=len(raw["text"]),
                page=raw.get("page"),
                order_index=chunk_counter,
                doc_year=raw.get("doc_year"),
                section_type_hint=raw.get("section_type"),
                metric_keywords=list(raw.get("metrics", []) or []),
            ))
            chunk_counter += 1

    # 등록 순서대로 정렬 (Python 3.7+ dict는 insertion-ordered이므로 그대로)
    return list(sections_by_title.values())


def parse_document(
    path: Path,
    *,
    doc_id: str | None = None,
    doc_type: DocType | None = None,
) -> Document:
    """
    파일 1개를 받아 Layer A Document 객체로 변환한다.

    파이프라인:
      1) doc_parser.parse(path) → markdown 문자열 (회사 레포 그대로)
      2) chunker.chunk(text)    → list[Chunk(TypedDict)] (회사 레포 그대로)
      3) chunks_to_layer_a()    → list[Section] (Layer A로 변환)

    Args:
        path:     입력 파일 경로 (.pdf/.docx/.doc/.hwp/.hwpx)
        doc_id:   명시 ID. 미지정 시 파일 SHA-256 앞 16자.
        doc_type: 명시 doc_type. 미지정 시 파일명 휴리스틱.

    Returns:
        Document 객체 (sections/chunks/tables가 채워진 상태).
        Document.publisher, fiscal_year 등은 W3 메타 추출에서 채워질 예정이라 None.
    """
    if doc_id is None:
        doc_id = _file_hash(path)

    if doc_type is None:
        doc_type = _infer_doc_type(path.name)

    # 1) 파싱
    markdown = _doc_parser.parse(path)

    # 2) 청킹 (회사 레포 정책 그대로: 700/200/50)
    flat_chunks = _chunker.chunk(markdown)

    # 3) Layer A 변환
    sections = chunks_to_layer_a(flat_chunks, doc_id=doc_id, doc_type=doc_type)

    return Document(
        id=doc_id,
        filename=path.name,
        source_format=_detect_source_format(path),
        doc_type=doc_type,
        total_pages=0,  # W3 metadata 추출에서 채움 예정
        ingested_at=datetime.utcnow(),
        sections=sections,
    )
