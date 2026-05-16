"""Layer A/B 적재 — Neo4j MERGE 기반 idempotent ingest.

#13 (extractor) → #14 (linking) 의 출력을 받아 Neo4j Aura 에 Layer B 를,
#17 의 ingestion.Document 객체를 받아 Layer A 를 적재한다.

설계 원칙:
- **Idempotent**: MERGE 기반 — 재실행해도 중복 노드 안 생김
- **멀티 라벨**: Layer B Entity 노드는 `:Entity` (전역 검색) + 구체 타입 동시 부착
- **노드 키**: Layer B 는 `group_id` (NED), Layer A 는 `id` (file hash + 청크 idx)
- **Layer 분리**: Layer A 적재 시 Layer B 노드 안 만지고, 그 반대도 동일.
  연결은 별도 함수 `link_chunks_to_entities` 가 책임 — AGENTS.md 원칙
  "Layer 책임 섞지 않기" 준수.

#24 (Opik 트레이싱):
- 공개 진입점 3개 모두 `@track`: build_layer_a / build_layer_b / link_chunks_to_entities
- 개별 MERGE 호출은 부착 안 함 — 8문서 적재 시 span 폭증 방지

#17 (5/16 8문서 일괄):
- Layer A 적재 — doc-ontology.md §3-§4 의 Cypher 스키마 그대로 구현
- 청크 노드의 id 가 ingestion.adapter._chunk_id() 의 `{doc_id}:c{idx:04d}` 형식
- entity 의 local_id 는 extractor 옵션 3 으로 `{chunk_id}__ent_001` 형식 →
  parse_global_id 로 청크 역추적해 MENTIONS 관계 생성

관련 이슈: #15 (Layer B), #17 (Layer A + 8문서), #13/#14 (입력), #24 (Opik).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from kg.extractor import parse_global_id
from kg.linking import EntityGroup, LinkingResult
from kg.neo4j_client import Neo4jClient
from kg.ontology import EntityType, ExtractedEntity, ExtractedRelation, RelationType
from observability.tracing import track

# Layer A 모델 — ingestion 모듈에서 import. circular 방지를 위해 함수 안에서
# import 하지 않고 여기서 한 번만.
from ingestion.models import Chunk, ChunkType, Document, Section, Table

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 결과 타입
# ═══════════════════════════════════════════════════════════════════
@dataclass
class IngestResult:
    """build_layer_b() 의 적재 결과 수치."""

    nodes_merged:     int
    relations_merged: int
    relations_dropped: int  # local_id 매핑 실패로 drop 된 관계 수
    elapsed_sec:      float


@dataclass
class LayerAIngestResult:
    """build_layer_a() 의 적재 결과 수치."""

    documents_merged: int
    sections_merged:  int
    chunks_merged:    int
    tables_merged:    int
    next_relations:   int  # Chunk -[:NEXT]-> Chunk 개수
    elapsed_sec:      float


@dataclass
class MentionsResult:
    """link_chunks_to_entities() 의 적재 결과 수치."""

    mentions_merged:  int
    mentions_dropped: int   # chunk_id parse 실패 또는 entity 없음
    elapsed_sec:      float


# ═══════════════════════════════════════════════════════════════════
# 인덱스 / 제약 조건
# ═══════════════════════════════════════════════════════════════════
INDEX_QUERIES = [
    # Layer B
    "CREATE CONSTRAINT entity_group_id IF NOT EXISTS "
    "FOR (e:Entity) REQUIRE e.group_id IS UNIQUE",
    "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
    # Layer A — #17 추가. doc-ontology.md §3 의 4 노드 모두 id 유일.
    "CREATE CONSTRAINT document_id IF NOT EXISTS "
    "FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT section_id IF NOT EXISTS "
    "FOR (s:Section) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS "
    "FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT table_id IF NOT EXISTS "
    "FOR (t:Table) REQUIRE t.id IS UNIQUE",
]


def ensure_indexes(client: Neo4jClient) -> None:
    """인덱스·제약조건 멱등 생성. 최초 1회만 실제 적용."""
    for q in INDEX_QUERIES:
        client.write(q)
        logger.info("Index/constraint applied: %s", q.split("FOR")[0].strip())


# ═══════════════════════════════════════════════════════════════════
# Layer B — Entity 노드 / 관계
# ═══════════════════════════════════════════════════════════════════
# 멀티 라벨 — EntityType 값을 동적 라벨로 부착하면서도 공통 :Entity 도 부여.
# Cypher 는 라벨을 파라미터로 받을 수 없으므로 f-string 으로 조립 —
# 입력 EntityType.value 는 enum 에서 온 화이트리스트 (injection 없음).
ENTITY_MERGE_TEMPLATE = """
MERGE (e:Entity {{group_id: $group_id}})
SET e:{label}
SET e.name          = $name,
    e.entity_type   = $entity_type,
    e.aliases       = $aliases,
    e.member_count  = $member_count,
    e.updated_at    = timestamp()
RETURN e.group_id AS group_id
""".strip()


def _merge_group(client: Neo4jClient, group: EntityGroup) -> None:
    """한 그룹 → 하나의 :Entity:{Type} 노드."""
    query = ENTITY_MERGE_TEMPLATE.format(label=group.type.value)
    client.write(
        query,
        group_id=group.group_id,
        name=group.representative_name,
        entity_type=group.type.value,
        aliases=sorted({m.canonical for m in group.members}),  # 중복 제거
        member_count=len(group.members),
    )


RELATION_MERGE_TEMPLATE = """
MATCH (s:Entity {{group_id: $source_gid}})
MATCH (t:Entity {{group_id: $target_gid}})
MERGE (s)-[r:{rel_type}]->(t)
SET r.evidence   = $evidence,
    r.updated_at = timestamp()
RETURN type(r) AS rel_type
""".strip()


def _merge_relation(
    client: Neo4jClient,
    rel_type: RelationType,
    source_gid: str,
    target_gid: str,
    evidence: str,
) -> None:
    query = RELATION_MERGE_TEMPLATE.format(rel_type=rel_type.value)
    client.write(
        query,
        source_gid=source_gid,
        target_gid=target_gid,
        evidence=evidence,
    )


def _build_local_to_group(linking: LinkingResult) -> dict[str, str]:
    """ExtractedEntity.local_id → 그게 속한 EntityGroup.group_id.

    옵션 3 (#17) 이후 local_id 는 `{chunk_id}__ent_001` 형식 — global 유일.
    따라서 청크 간 충돌 없음.
    """
    mapping: dict[str, str] = {}
    for group in linking.groups:
        for member in group.members:
            mapping[member.local_id] = group.group_id
    return mapping


@track
def build_layer_b(
    linking: LinkingResult,
    relations: list[ExtractedRelation],
    *,
    client: Neo4jClient | None = None,
    create_indexes: bool = True,
) -> IngestResult:
    """Layer B 를 Neo4j 에 적재.

    파이프라인:
      1. (옵션) 인덱스/제약조건 멱등 생성
      2. 그룹별로 :Entity:{Type} 노드 MERGE
      3. local_id → group_id 매핑 구축
      4. 관계별로 MATCH-MATCH-MERGE
    """
    started = time.perf_counter()

    if client is None:
        client = Neo4jClient()

    if create_indexes:
        ensure_indexes(client)

    for group in linking.groups:
        _merge_group(client, group)
    nodes_merged = len(linking.groups)

    local_to_group = _build_local_to_group(linking)

    relations_merged  = 0
    relations_dropped = 0
    for rel in relations:
        src_gid = local_to_group.get(rel.source)
        tgt_gid = local_to_group.get(rel.target)
        if src_gid is None or tgt_gid is None:
            logger.warning(
                "Relation drop — local_id 매핑 실패 (source=%s -> %s, target=%s -> %s)",
                rel.source, src_gid, rel.target, tgt_gid,
            )
            relations_dropped += 1
            continue
        _merge_relation(client, rel.type, src_gid, tgt_gid, rel.evidence or "")
        relations_merged += 1

    elapsed = time.perf_counter() - started
    result = IngestResult(
        nodes_merged=nodes_merged,
        relations_merged=relations_merged,
        relations_dropped=relations_dropped,
        elapsed_sec=elapsed,
    )
    logger.info(
        "Layer B 적재 완료 nodes=%d relations=%d dropped=%d (%.2fs)",
        result.nodes_merged, result.relations_merged, result.relations_dropped, result.elapsed_sec,
    )
    return result


# ═══════════════════════════════════════════════════════════════════
# Layer A — Document / Section / Chunk / Table (#17)
# ═══════════════════════════════════════════════════════════════════
# 노드 MERGE 템플릿. doc-ontology.md §3.1-3.4 스키마 그대로.

DOCUMENT_MERGE = """
MERGE (d:Document {id: $id})
SET d.filename       = $filename,
    d.doc_type       = $doc_type,
    d.source_format  = $source_format,
    d.total_pages    = $total_pages,
    d.publisher      = $publisher,
    d.subject        = $subject,
    d.fiscal_year    = $fiscal_year,
    d.ingested_at    = timestamp()
RETURN d.id AS id
""".strip()


SECTION_MERGE = """
MERGE (s:Section {id: $id})
SET s.label             = $label,
    s.doc_type          = $doc_type,
    s.original_section  = $original_section,
    s.heading_level     = $heading_level,
    s.order_index       = $order_index,
    s.page_start        = $page_start,
    s.page_end          = $page_end,
    s.updated_at        = timestamp()
RETURN s.id AS id
""".strip()


CHUNK_MERGE = """
MERGE (c:Chunk {id: $id})
SET c.text         = $text,
    c.chunk_type   = $chunk_type,
    c.char_count   = $char_count,
    c.page         = $page,
    c.order_index  = $order_index,
    c.updated_at   = timestamp()
RETURN c.id AS id
""".strip()


TABLE_MERGE = """
MERGE (t:Table {id: $id})
SET t.raw_markdown  = $raw_markdown,
    t.caption       = $caption,
    t.row_count     = $row_count,
    t.column_count  = $column_count,
    t.page          = $page,
    t.order_index   = $order_index,
    t.updated_at    = timestamp()
RETURN t.id AS id
""".strip()


# 관계 MERGE — Layer A 의 4 관계 (doc-ontology.md §4)
HAS_SECTION_MERGE = """
MATCH (d:Document {id: $doc_id})
MATCH (s:Section  {id: $section_id})
MERGE (d)-[:HAS_SECTION]->(s)
""".strip()


CONTAINS_CHUNK_MERGE = """
MATCH (s:Section {id: $section_id})
MATCH (c:Chunk   {id: $chunk_id})
MERGE (s)-[:CONTAINS_CHUNK]->(c)
""".strip()


CONTAINS_TABLE_MERGE = """
MATCH (s:Section {id: $section_id})
MATCH (t:Table   {id: $table_id})
MERGE (s)-[:CONTAINS_TABLE]->(t)
""".strip()


NEXT_CHUNK_MERGE = """
MATCH (a:Chunk {id: $prev_id})
MATCH (b:Chunk {id: $next_id})
MERGE (a)-[:NEXT]->(b)
""".strip()


def _merge_document(client: Neo4jClient, doc: Document) -> None:
    """Document 노드 MERGE."""
    client.write(
        DOCUMENT_MERGE,
        id=doc.id,
        filename=doc.filename,
        doc_type=doc.doc_type.value,
        source_format=doc.source_format.value,
        total_pages=doc.total_pages,
        publisher=doc.publisher,
        subject=doc.subject,
        fiscal_year=doc.fiscal_year,
    )


def _merge_section(client: Neo4jClient, section: Section) -> None:
    """Section 노드 MERGE — label 은 W3 LLM 채움 전이라 None 가능."""
    client.write(
        SECTION_MERGE,
        id=section.id,
        label=section.label.value if section.label else None,
        doc_type=section.doc_type.value,
        original_section=section.original_section,
        heading_level=section.heading_level,
        order_index=section.order_index,
        page_start=section.page_start,
        page_end=section.page_end,
    )


def _merge_chunk(client: Neo4jClient, chunk: Chunk) -> None:
    """Chunk 노드 MERGE."""
    client.write(
        CHUNK_MERGE,
        id=chunk.id,
        text=chunk.text,
        chunk_type=chunk.chunk_type.value,
        char_count=chunk.char_count,
        page=chunk.page,
        order_index=chunk.order_index,
    )


def _merge_table(client: Neo4jClient, table: Table) -> None:
    """Table 노드 MERGE."""
    client.write(
        TABLE_MERGE,
        id=table.id,
        raw_markdown=table.raw_markdown,
        caption=table.caption,
        row_count=table.row_count,
        column_count=table.column_count,
        page=table.page,
        order_index=table.order_index,
    )


@track(ignore_arguments=["client"])
def build_layer_a(
    document: Document,
    *,
    client: Neo4jClient | None = None,
    create_indexes: bool = True,
) -> LayerAIngestResult:
    """Layer A (Document Structure) 를 Neo4j 에 적재.

    파이프라인 (doc-ontology.md §3-§4):
      1. (옵션) Layer A 인덱스/제약조건 멱등 생성
      2. Document 노드 MERGE
      3. Section 노드들 MERGE + HAS_SECTION 관계
      4. Chunk / Table 노드들 MERGE + CONTAINS_CHUNK / CONTAINS_TABLE 관계
      5. Section 내 Chunk 순서대로 NEXT 관계

    Args:
        document:       ingestion.adapter.parse_document() 출력
        client:         Neo4jClient 주입 (테스트 재활용). None 이면 from_env.
        create_indexes: 첫 적재 시 인덱스 생성 시도 (멱등).

    Returns:
        LayerAIngestResult — 노드/관계 적재 수치.

    #24 Opik:
    - 본 함수에 `@track(ignore_arguments=["client"])` — client 객체가
      `<...object at 0x...>` 로 박혀 노이즈가 되는 것 회피 (5/16 박제).
    """
    started = time.perf_counter()

    if client is None:
        client = Neo4jClient()

    if create_indexes:
        ensure_indexes(client)

    # 2. Document
    _merge_document(client, document)
    documents_merged = 1

    sections_merged = 0
    chunks_merged   = 0
    tables_merged   = 0
    next_relations  = 0

    # 3-5. Section / Chunk / Table / 관계
    for section in document.sections:
        _merge_section(client, section)
        client.write(HAS_SECTION_MERGE, doc_id=document.id, section_id=section.id)
        sections_merged += 1

        prev_chunk_id: str | None = None
        for chunk in section.chunks:
            _merge_chunk(client, chunk)
            client.write(
                CONTAINS_CHUNK_MERGE,
                section_id=section.id,
                chunk_id=chunk.id,
            )
            chunks_merged += 1

            # Section 내 Chunk NEXT 관계
            if prev_chunk_id is not None:
                client.write(
                    NEXT_CHUNK_MERGE,
                    prev_id=prev_chunk_id,
                    next_id=chunk.id,
                )
                next_relations += 1
            prev_chunk_id = chunk.id

        for table in section.tables:
            _merge_table(client, table)
            client.write(
                CONTAINS_TABLE_MERGE,
                section_id=section.id,
                table_id=table.id,
            )
            tables_merged += 1

    elapsed = time.perf_counter() - started
    result = LayerAIngestResult(
        documents_merged=documents_merged,
        sections_merged=sections_merged,
        chunks_merged=chunks_merged,
        tables_merged=tables_merged,
        next_relations=next_relations,
        elapsed_sec=elapsed,
    )
    logger.info(
        "Layer A 적재 완료 doc=%s sections=%d chunks=%d tables=%d next=%d (%.2fs)",
        document.filename,
        result.sections_merged, result.chunks_merged,
        result.tables_merged, result.next_relations,
        result.elapsed_sec,
    )
    return result


# ═══════════════════════════════════════════════════════════════════
# MENTIONS — Layer A Chunk → Layer B Entity (#17)
# ═══════════════════════════════════════════════════════════════════
MENTIONS_MERGE = """
MATCH (c:Chunk  {id: $chunk_id})
MATCH (e:Entity {group_id: $group_id})
MERGE (c)-[:MENTIONS]->(e)
""".strip()


@track(ignore_arguments=["client"])
def link_chunks_to_entities(
    linking: LinkingResult,
    *,
    client: Neo4jClient | None = None,
) -> MentionsResult:
    """Layer A Chunk 와 Layer B Entity 를 MENTIONS 관계로 연결.

    동작:
      - linking.groups 의 각 EntityGroup.members 를 순회
      - 각 member 의 local_id 에서 `parse_global_id` 로 chunk_id 추출
      - `(:Chunk {id: chunk_id}) -[:MENTIONS]-> (:Entity {group_id: group.group_id})`

    chunk_id 가 없는 (구식, 5/10 sanity) entity 는 graceful drop — Layer A
    가 적재 안 됐을 가능성 높으므로 매핑 불가.

    Args:
        linking: #14 출력 (그룹화된 Entity 들). 각 member 의 local_id 가
                 `{chunk_id}__ent_001` 형식이어야 매핑 가능 (옵션 3).
        client:  Neo4jClient 주입. None 이면 from_env.

    Returns:
        MentionsResult — 적재 / drop 수치.
    """
    started = time.perf_counter()

    if client is None:
        client = Neo4jClient()

    mentions_merged  = 0
    mentions_dropped = 0

    for group in linking.groups:
        # 같은 그룹 안에서 동일 청크가 여러 member 로 등장할 수 있음 (드물게).
        # MERGE 가 idempotent 라 여러 번 호출해도 안전하지만 통계는 정확히
        # 청크별 1회로 집계.
        seen_chunks: set[str] = set()
        for member in group.members:
            chunk_id, _ = parse_global_id(member.local_id)
            if chunk_id is None:
                # 구식 local_id — Layer A 매핑 불가. 5/10 sanity 호환.
                mentions_dropped += 1
                continue
            if chunk_id in seen_chunks:
                continue
            seen_chunks.add(chunk_id)

            client.write(
                MENTIONS_MERGE,
                chunk_id=chunk_id,
                group_id=group.group_id,
            )
            mentions_merged += 1

    elapsed = time.perf_counter() - started
    result = MentionsResult(
        mentions_merged=mentions_merged,
        mentions_dropped=mentions_dropped,
        elapsed_sec=elapsed,
    )
    logger.info(
        "MENTIONS 적재 완료 merged=%d dropped=%d (%.2fs)",
        result.mentions_merged, result.mentions_dropped, result.elapsed_sec,
    )
    return result
