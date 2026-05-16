"""kg/builder.py 의 Layer A 함수 + MENTIONS 매핑 단위 테스트.

검증 포인트 (#17):
- build_layer_a: Document/Section/Chunk/Table MERGE 호출 + 관계 4종
- 청크 NEXT 관계: Section 내 순서대로만 (Section 경계 넘지 않음)
- link_chunks_to_entities: parse_global_id 로 chunk_id 추출 후 MENTIONS
- chunk_id 없는 구식 local_id 는 graceful drop (5/10 호환)

테스트 방식: mock Neo4jClient — 실제 DB 없이 client.write() 호출 인자 검증.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from ingestion.models import (
    Chunk as LayerAChunk,
    ChunkType,
    DocType,
    Document,
    Section,
    SectionLabel,
    SourceFormat,
    Table,
)
from kg.builder import build_layer_a, link_chunks_to_entities
from kg.linking import EntityGroup, LinkingResult
from kg.ontology import EntityType, ExtractedEntity


# ── Mock Neo4jClient ──────────────────────────────────────
@dataclass
class _MockClient:
    """Neo4jClient 인터페이스 흉내 — write() 호출을 기록만 함."""

    writes: list[tuple[str, dict]] = field(default_factory=list)

    def write(self, query: str, **params) -> list:
        self.writes.append((query, params))
        return []

    def read(self, query: str, **params) -> list:
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _writes_with_keyword(client: _MockClient, keyword: str) -> list[tuple[str, dict]]:
    """write 호출 중 query 에 keyword 포함된 것만."""
    return [(q, p) for q, p in client.writes if keyword in q]


# ── 픽스처: 두산밥캣 mini Document ──────────────────────────
@pytest.fixture
def doosan_doc() -> Document:
    """1 Document + 2 Section + 3 Chunk + 1 Table 의 미니 문서."""
    section1 = Section(
        id="doc1:s000",
        original_section="3분기 실적",
        doc_type=DocType.REPORT,
        label=SectionLabel.PERFORMANCE,
        heading_level=2,
        order_index=0,
        page_start=3,
        page_end=4,
        chunks=[
            LayerAChunk(
                id="doc1:c0000",
                text="두산밥캣 영업이익 35% 감소.",
                chunk_type=ChunkType.TEXT,
                char_count=20,
                page=3,
                order_index=0,
            ),
            LayerAChunk(
                id="doc1:c0001",
                text="북미 고금리 장기화가 원인.",
                chunk_type=ChunkType.TEXT,
                char_count=18,
                page=3,
                order_index=1,
            ),
        ],
        tables=[
            Table(
                id="doc1:t000",
                raw_markdown="| 항목 | 값 |\n|---|---|\n| 영업이익 | 1.2조 |",
                row_count=3,
                column_count=2,
                page=4,
                order_index=0,
            ),
        ],
    )
    section2 = Section(
        id="doc1:s001",
        original_section="전망",
        doc_type=DocType.REPORT,
        label=SectionLabel.OUTLOOK,
        heading_level=2,
        order_index=1,
        chunks=[
            LayerAChunk(
                id="doc1:c0002",
                text="2026 회복 전망.",
                chunk_type=ChunkType.TEXT,
                char_count=10,
                page=5,
                order_index=2,
            ),
        ],
    )
    return Document(
        id="doc1",
        filename="한화_두산밥캣.pdf",
        source_format=SourceFormat.PDF,
        doc_type=DocType.REPORT,
        total_pages=5,
        publisher="한화투자증권",
        subject="두산밥캣",
        fiscal_year=2024,
        sections=[section1, section2],
    )


# ── build_layer_a 테스트 ──────────────────────────────────
def test_build_layer_a_node_counts(doosan_doc: Document):
    """Document 1 + Section 2 + Chunk 3 + Table 1 노드 MERGE 발생."""
    client = _MockClient()
    result = build_layer_a(doosan_doc, client=client, create_indexes=False)

    assert result.documents_merged == 1
    assert result.sections_merged == 2
    assert result.chunks_merged == 3
    assert result.tables_merged == 1


def test_build_layer_a_document_params(doosan_doc: Document):
    """Document MERGE 에 publisher / fiscal_year 등 메타 정확히 전달."""
    client = _MockClient()
    build_layer_a(doosan_doc, client=client, create_indexes=False)

    doc_writes = _writes_with_keyword(client, "MERGE (d:Document")
    assert len(doc_writes) == 1
    _, params = doc_writes[0]
    assert params["id"] == "doc1"
    assert params["filename"] == "한화_두산밥캣.pdf"
    assert params["doc_type"] == "report"
    assert params["source_format"] == "pdf"
    assert params["publisher"] == "한화투자증권"
    assert params["fiscal_year"] == 2024


def test_build_layer_a_section_label_serialized(doosan_doc: Document):
    """Section.label (enum) → 문자열 값으로 직렬화."""
    client = _MockClient()
    build_layer_a(doosan_doc, client=client, create_indexes=False)

    section_writes = _writes_with_keyword(client, "MERGE (s:Section")
    assert len(section_writes) == 2
    labels = {p["label"] for _, p in section_writes}
    assert labels == {"Performance", "Outlook"}


def test_build_layer_a_section_label_none_safe():
    """Section.label 이 None 이어도 적재 가능 (W3 미분류 청크 대응)."""
    doc = Document(
        id="d", filename="t.pdf", source_format=SourceFormat.PDF,
        doc_type=DocType.IR, total_pages=1,
        sections=[
            Section(
                id="s", original_section="raw", doc_type=DocType.IR,
                label=None,  # ← 미분류
            ),
        ],
    )
    client = _MockClient()
    build_layer_a(doc, client=client, create_indexes=False)
    section_writes = _writes_with_keyword(client, "MERGE (s:Section")
    _, params = section_writes[0]
    assert params["label"] is None


def test_build_layer_a_next_relations_only_within_section(doosan_doc: Document):
    """NEXT 관계는 Section 내에서만. Section 경계 넘지 않음."""
    client = _MockClient()
    result = build_layer_a(doosan_doc, client=client, create_indexes=False)

    # section1: chunks c0000 → c0001 (1개), section2: c0002 단독 (0개)
    assert result.next_relations == 1

    next_writes = _writes_with_keyword(client, "[:NEXT]")
    assert len(next_writes) == 1
    _, params = next_writes[0]
    assert params["prev_id"] == "doc1:c0000"
    assert params["next_id"] == "doc1:c0001"


def test_build_layer_a_table_attached_to_section(doosan_doc: Document):
    """CONTAINS_TABLE 관계가 올바른 Section 에 연결."""
    client = _MockClient()
    build_layer_a(doosan_doc, client=client, create_indexes=False)

    table_writes = _writes_with_keyword(client, "[:CONTAINS_TABLE]")
    assert len(table_writes) == 1
    _, params = table_writes[0]
    assert params["section_id"] == "doc1:s000"
    assert params["table_id"] == "doc1:t000"


def test_build_layer_a_idempotent_uses_merge(doosan_doc: Document):
    """모든 쿼리가 MERGE 기반 (idempotent). CREATE 단독 없음."""
    client = _MockClient()
    build_layer_a(doosan_doc, client=client, create_indexes=False)

    for query, _ in client.writes:
        # CREATE CONSTRAINT/INDEX 는 create_indexes=False 라 호출 안 됨
        assert "MERGE" in query


# ── link_chunks_to_entities 테스트 ────────────────────────
def _make_group(group_id: str, type_: EntityType, members: list[ExtractedEntity]) -> EntityGroup:
    return EntityGroup(
        group_id=group_id,
        type=type_,
        representative_name=members[0].canonical if members else "",
        members=members,
    )


def test_link_chunks_to_entities_basic():
    """각 EntityGroup.member 마다 chunk_id 를 추출해 MENTIONS MERGE."""
    linking = LinkingResult(
        groups=[
            _make_group(
                "grp_001",
                EntityType.COMPANY,
                [
                    ExtractedEntity(
                        local_id="doc1:c0000__ent_001",
                        type=EntityType.COMPANY,
                        canonical="두산밥캣",
                        source_span="두산밥캣",
                        section="3분기 실적",
                    ),
                ],
            ),
            _make_group(
                "grp_002",
                EntityType.METRIC,
                [
                    ExtractedEntity(
                        local_id="doc1:c0000__ent_002",
                        type=EntityType.METRIC,
                        canonical="영업이익 -35%",
                        source_span="영업이익이 전년 동기 대비 35% 감소",
                        section="3분기 실적",
                    ),
                ],
            ),
        ],
        raw_count=2,
        grouped_count=2,
    )

    client = _MockClient()
    result = link_chunks_to_entities(linking, client=client)

    assert result.mentions_merged == 2
    assert result.mentions_dropped == 0

    # 각 MENTIONS write 가 올바른 chunk_id + group_id 를 가지는지
    mentions = _writes_with_keyword(client, "[:MENTIONS]")
    assert len(mentions) == 2
    pairs = {(p["chunk_id"], p["group_id"]) for _, p in mentions}
    assert pairs == {
        ("doc1:c0000", "grp_001"),
        ("doc1:c0000", "grp_002"),
    }


def test_link_chunks_to_entities_dedupe_same_chunk():
    """한 그룹 내 같은 청크의 member 가 여러 개여도 청크당 1회만 MENTIONS."""
    linking = LinkingResult(
        groups=[
            _make_group(
                "grp_001",
                EntityType.COMPANY,
                [
                    # 같은 청크에서 같은 그룹의 alias 가 2번 등장 (드물지만 가능)
                    ExtractedEntity(
                        local_id="doc1:c0000__ent_001",
                        type=EntityType.COMPANY, canonical="두산밥캣",
                        source_span="두산밥캣", section="3분기",
                    ),
                    ExtractedEntity(
                        local_id="doc1:c0000__ent_003",
                        type=EntityType.COMPANY, canonical="Doosan Bobcat",
                        source_span="Doosan Bobcat", section="3분기",
                    ),
                ],
            ),
        ],
        raw_count=2,
        grouped_count=1,
    )

    client = _MockClient()
    result = link_chunks_to_entities(linking, client=client)

    # 청크 1개, 그룹 1개 → MENTIONS 1번만
    assert result.mentions_merged == 1
    mentions = _writes_with_keyword(client, "[:MENTIONS]")
    assert len(mentions) == 1


def test_link_chunks_to_entities_multi_chunk_same_group():
    """다른 청크의 member 들은 각각 MENTIONS — 청크당 1번씩."""
    linking = LinkingResult(
        groups=[
            _make_group(
                "grp_001",
                EntityType.COMPANY,
                [
                    ExtractedEntity(
                        local_id="doc1:c0000__ent_001",
                        type=EntityType.COMPANY, canonical="미래에셋",
                        source_span="미래에셋", section="1Q",
                    ),
                    ExtractedEntity(
                        local_id="doc1:c0010__ent_001",
                        type=EntityType.COMPANY, canonical="미래에셋증권",
                        source_span="미래에셋증권", section="2Q",
                    ),
                    ExtractedEntity(
                        local_id="doc1:c0020__ent_002",
                        type=EntityType.COMPANY, canonical="미래에셋",
                        source_span="미래에셋", section="3Q",
                    ),
                ],
            ),
        ],
        raw_count=3,
        grouped_count=1,
    )

    client = _MockClient()
    result = link_chunks_to_entities(linking, client=client)

    # 3개 청크 → 3개 MENTIONS
    assert result.mentions_merged == 3
    mentions = _writes_with_keyword(client, "[:MENTIONS]")
    chunk_ids = sorted({p["chunk_id"] for _, p in mentions})
    assert chunk_ids == ["doc1:c0000", "doc1:c0010", "doc1:c0020"]


def test_link_chunks_to_entities_legacy_local_id_dropped():
    """chunk_id prefix 없는 구식 local_id 는 graceful drop (5/10 sanity 호환)."""
    linking = LinkingResult(
        groups=[
            _make_group(
                "grp_001",
                EntityType.COMPANY,
                [
                    ExtractedEntity(
                        local_id="ent_001",  # ← prefix 없음
                        type=EntityType.COMPANY, canonical="두산밥캣",
                        source_span="두산밥캣", section="3분기",
                    ),
                ],
            ),
        ],
        raw_count=1,
        grouped_count=1,
    )

    client = _MockClient()
    result = link_chunks_to_entities(linking, client=client)

    assert result.mentions_merged == 0
    assert result.mentions_dropped == 1
    # 실제 write 호출 없음
    assert _writes_with_keyword(client, "[:MENTIONS]") == []
