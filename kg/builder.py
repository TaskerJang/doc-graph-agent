"""Layer B 적재 — LinkingResult + Relations → Neo4j MERGE.

#13 (extractor) → #14 (linking) 의 출력을 받아 Neo4j Aura 에 Layer B 를
적재한다. Layer A (Document/Section/Chunk) 는 5/14 보너스에서.

설계 원칙:
- **Idempotent**: MERGE 기반 — 재실행해도 중복 노드 안 생김
- **멀티 라벨**: 모든 Entity 노드에 `:Entity` (전역 검색용) + 구체 타입
  (`:Company` `:Metric` `:Recommendation` `:Risk` `:Outlook`) 동시 부착
- **노드 키**: `group_id` (NED 가 부여한 전역 ID) — 같은 그룹이면 같은 노드
- **관계**: ExtractedRelation.source/target (청크 내 local_id) 는 NED 단계에
  group_id 로 매핑하는 보조 테이블 필요 — 본 모듈이 책임

관련 이슈: #15 (본), #13/#14 (입력 공급), #16 (후속 — 시각화).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from kg.linking import EntityGroup, LinkingResult
from kg.neo4j_client import Neo4jClient
from kg.ontology import EntityType, ExtractedEntity, ExtractedRelation, RelationType

logger = logging.getLogger(__name__)


# ── 결과 타입 ───────────────────────────────────────────
@dataclass
class IngestResult:
    """build_layer_b() 의 적재 결과 수치."""

    nodes_merged:     int
    relations_merged: int
    relations_dropped: int  # local_id 매핑 실패로 drop 된 관계 수
    elapsed_sec:      float


# ── 인덱스 / 제약 조건 ───────────────────────────────────
INDEX_QUERIES = [
    # group_id 유일 제약 — 동시에 B-tree 인덱스 역할
    "CREATE CONSTRAINT entity_group_id IF NOT EXISTS "
    "FOR (e:Entity) REQUIRE e.group_id IS UNIQUE",
    # name 검색 가속 (유일 제약 아님 — 동명 회사·메트릭 가능)
    "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
]


def ensure_indexes(client: Neo4jClient) -> None:
    """인덱스·제약조건 멱등 생성. 최초 1회만 실제 적용."""
    for q in INDEX_QUERIES:
        client.write(q)
        logger.info("Index/constraint applied: %s", q.split("FOR")[0].strip())


# ── 노드 MERGE ──────────────────────────────────────────
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


# ── 관계 MERGE ─────────────────────────────────────────
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


# ── local_id → group_id 매핑 ──────────────────────────────────
def _build_local_to_group(linking: LinkingResult) -> dict[str, str]:
    """ExtractedEntity.local_id → 그게 속한 EntityGroup.group_id.

    ExtractedRelation 은 source/target 으로 local_id 를 싨는데 (추출 당시의 ID),
    적재 시점에는 NED 그룹 기준으로 연결해야 하므로 매핑 필요.

    주의: local_id 는 청크 간 중복 가능 (각 청크가 ent_001 부터 시작).
    실제 운영에서는 (chunk_idx, local_id) 튜플이 key 여야 안전.
    본 PR 은 1청크 시나리오만 취급 — #17 에서 다중 청크 시 결합.
    """
    mapping: dict[str, str] = {}
    for group in linking.groups:
        for member in group.members:
            mapping[member.local_id] = group.group_id
    return mapping


# ── 공개 인터페이스 ───────────────────────────────────────
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
      4. 관계별로 MATCH-MATCH-MERGE (양쪽 그룹 존재 필수)

    Args:
        linking:        #14 출력 (그룹화된 Entity 들)
        relations:      #13 출력 (청크 내 local_id 기반 관계)
        client:         Neo4jClient 를 주입 (테스트·CLI 재활용). None 이면 from_env.
        create_indexes: 첨 적재 시 인덱스 생성 시도 (멱등).

    Returns:
        IngestResult — 적재 수치.
    """
    started = time.perf_counter()

    if client is None:
        client = Neo4jClient()  # from_env

    if create_indexes:
        ensure_indexes(client)

    # 2. 노드 MERGE
    for group in linking.groups:
        _merge_group(client, group)
    nodes_merged = len(linking.groups)

    # 3. local_id → group_id
    local_to_group = _build_local_to_group(linking)

    # 4. 관계 MERGE
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
