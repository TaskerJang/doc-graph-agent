"""kg/builder.py 단위 테스트.

Neo4jClient 를 mock 으로 대체. 실제 적재는 PR 본문의 통합 스크립트에서 검증.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from kg.builder import build_layer_b
from kg.linking import EntityGroup, LinkingResult
from kg.ontology import (
    EntityType,
    ExtractedEntity,
    ExtractedRelation,
    RelationType,
)


# ── helper ──────────────────────────────────────────────
def _ent(local_id: str, type_: EntityType, canonical: str) -> ExtractedEntity:
    return ExtractedEntity(
        local_id=local_id,
        type=type_,
        canonical=canonical,
        source_span=canonical,
        section="S",
    )


def _mock_client() -> MagicMock:
    c = MagicMock()
    c.write = MagicMock(return_value=[])
    return c


# ── 테스트 ────────────────────────────────────────────────
def test_build_layer_b_empty_input():
    """빈 입력 → 인덱스만 생성, 노드/관계 0."""
    linking = LinkingResult(groups=[], raw_count=0, grouped_count=0)
    relations: list[ExtractedRelation] = []
    client = _mock_client()

    result = build_layer_b(linking, relations, client=client, create_indexes=True)

    assert result.nodes_merged == 0
    assert result.relations_merged == 0
    assert result.relations_dropped == 0
    # 인덱스 2개만 write 됨 (CREATE CONSTRAINT + CREATE INDEX)
    assert client.write.call_count == 2


def test_build_layer_b_doosan_one_chunk():
    """두산밥캣 1청크 시나리오 — #16 시각화의 최소 그래프.

    3 그룹 (Company · Metric · Risk) + 2 관계 (HAS_METRIC · FACES_RISK)
    PR #38 실제 Kimi 호출 산출물 그대로.
    """
    e1 = _ent("ent_001", EntityType.COMPANY, "두산밥캣")
    e2 = _ent("ent_002", EntityType.METRIC, "영업이익 전년 동기 대비 35% 감소 (2024Q3)")
    e3 = _ent("ent_003", EntityType.RISK, "북미 고금리 장기화에 따른 건설장비 수요 둔화")

    linking = LinkingResult(
        groups=[
            EntityGroup(group_id="grp_001", type=EntityType.COMPANY, representative_name="두산밥캣", members=[e1]),
            EntityGroup(group_id="grp_002", type=EntityType.METRIC, representative_name=e2.canonical, members=[e2]),
            EntityGroup(group_id="grp_003", type=EntityType.RISK, representative_name=e3.canonical, members=[e3]),
        ],
        raw_count=3,
        grouped_count=3,
    )
    relations = [
        ExtractedRelation(source="ent_001", type=RelationType.HAS_METRIC, target="ent_002", evidence="공시"),
        ExtractedRelation(source="ent_001", type=RelationType.FACES_RISK, target="ent_003", evidence="주된 원인"),
    ]
    client = _mock_client()

    result = build_layer_b(linking, relations, client=client, create_indexes=False)

    assert result.nodes_merged == 3
    assert result.relations_merged == 2
    assert result.relations_dropped == 0
    # 3 그룹 MERGE + 2 관계 MERGE = 5 write
    assert client.write.call_count == 5

    # MERGE 쿼리에 라벨이 올바르게 삽입되었는지
    queries = [call.args[0] for call in client.write.call_args_list]
    assert any("e:Company" in q for q in queries)
    assert any("e:Metric" in q for q in queries)
    assert any("e:Risk" in q for q in queries)
    assert any("r:HAS_METRIC" in q for q in queries)
    assert any("r:FACES_RISK" in q for q in queries)


def test_build_layer_b_dangling_relation_dropped():
    """관계의 source/target 이 그룹 매핑에 없으면 graceful drop."""
    e1 = _ent("ent_001", EntityType.COMPANY, "두산밥캣")
    linking = LinkingResult(
        groups=[
            EntityGroup(group_id="grp_001", type=EntityType.COMPANY, representative_name="두산밥캣", members=[e1]),
        ],
        raw_count=1,
        grouped_count=1,
    )
    relations = [
        # ent_999 는 linking 에 없음 → drop
        ExtractedRelation(source="ent_001", type=RelationType.HAS_METRIC, target="ent_999", evidence="X"),
    ]
    client = _mock_client()

    result = build_layer_b(linking, relations, client=client, create_indexes=False)

    assert result.nodes_merged == 1
    assert result.relations_merged == 0
    assert result.relations_dropped == 1
    # 노드 1 MERGE 만 — 관계 입력 자체가 스킵
    assert client.write.call_count == 1


def test_build_layer_b_aliases_deduplicated():
    """그룹 멤버 canonical 이 중복이면 aliases 에서 제거."""
    e1 = _ent("ent_001", EntityType.COMPANY, "두산밥캣")
    e2 = _ent("ent_002", EntityType.COMPANY, "두산밥캣")  # 동일 canonical
    e3 = _ent("ent_003", EntityType.COMPANY, "두산밥캣㈈")
    linking = LinkingResult(
        groups=[
            EntityGroup(
                group_id="grp_001",
                type=EntityType.COMPANY,
                representative_name="두산밥캣㈈",
                members=[e1, e2, e3],
            ),
        ],
        raw_count=3,
        grouped_count=1,
    )
    client = _mock_client()

    build_layer_b(linking, [], client=client, create_indexes=False)

    # MERGE 호출 의 aliases 파라미터 확인
    call = client.write.call_args_list[0]
    aliases = call.kwargs["aliases"]
    assert sorted(aliases) == sorted(["두산밥캣", "두산밥캣㈈"])  # 중복 1개 제거됨
    assert call.kwargs["member_count"] == 3  # 멤버는 3 유지
