"""W3 파이프라인 end-to-end 통합 스크립트.

두산밥캣 1청크 → extract (#13) → linking (#14) → build_layer_b (#15) → Neo4j 적재
→ 적재 후 Cypher 검증 조회까지 명령행 한번에.

사용:
    uv run python scripts/run_w3_pipeline.py

전제조건:
    .env 에 KIMI_API_KEY / NEO4J_URI / NEO4J_PASSWORD
    bge-m3 최초 1회 다운로드 완료 상태 (#14 검증 때 다운로드됨)

#16 시각화: 적재 완료 이후 Aura 콘솔 또는 Neo4j Browser 에서
    MATCH (n:Entity) RETURN n LIMIT 50
    으로 시각화 가능.
"""

from __future__ import annotations

import asyncio
import logging

from kg.builder import build_layer_b
from kg.extractor import extract
from kg.linking import link_entities
from kg.neo4j_client import Neo4jClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("w3-pipeline")


DOOSAN_TEXT = (
    "두산밥캣은 2024년 3분기 영업이익이 전년 동기 대비 35% 감소했다고 공시했다. "
    "북미 시장의 고금리 장기화로 건설장비 수요가 둔화된 것이 주된 원인이다."
)


async def main() -> None:
    chunks = [
        {
            "doc_id":  "doosan-2024Q3",
            "section": "3분기 실적",
            "text":    DOOSAN_TEXT,
        }
    ]

    # 1. Extract (Kimi)
    logger.info("=== 1. Extract 시작 ===")
    ext_result = await extract(chunks)
    logger.info(
        "Extract 결과 entities=%d relations=%d",
        len(ext_result.entities), len(ext_result.relations),
    )
    for e in ext_result.entities:
        logger.info("  Entity (%s) %s", e.type.value, e.canonical)
    for r in ext_result.relations:
        logger.info("  Relation %s -[%s]-> %s", r.source, r.type.value, r.target)

    # 2. Linking (bge-m3)
    logger.info("=== 2. Linking 시작 ===")
    link_result = link_entities(ext_result.entities)
    logger.info(
        "Linking 결과 raw=%d -> groups=%d (compression=%.2f)",
        link_result.raw_count, link_result.grouped_count, link_result.compression_ratio,
    )
    for g in link_result.groups:
        logger.info("  [%s] %s %s", g.group_id, g.type.value, g.representative_name)

    # 3. Build Layer B → Neo4j
    logger.info("=== 3. Neo4j 적재 시작 ===")
    with Neo4jClient() as client:
        client.verify_connectivity()
        ingest = build_layer_b(
            link_result,
            ext_result.relations,
            client=client,
            create_indexes=True,
        )
        logger.info(
            "적재 완료 nodes=%d relations=%d dropped=%d (%.2fs)",
            ingest.nodes_merged, ingest.relations_merged,
            ingest.relations_dropped, ingest.elapsed_sec,
        )

        # 4. 검증 조회 — 적재된 노드/관계 둘러보기
        logger.info("=== 4. Cypher 검증 조회 ===")
        nodes = client.read("MATCH (e:Entity) RETURN e.group_id AS gid, e.entity_type AS type, e.name AS name ORDER BY e.group_id")
        for n in nodes:
            logger.info("  Node %s [%s] %s", n["gid"], n["type"], n["name"])

        rels = client.read(
            "MATCH (s:Entity)-[r]->(t:Entity) "
            "RETURN s.name AS src, type(r) AS rel, t.name AS tgt, r.evidence AS evidence "
            "ORDER BY type(r)"
        )
        for r in rels:
            logger.info("  Rel  (%s) -[%s]-> (%s)  | %s", r["src"], r["rel"], r["tgt"], (r["evidence"] or "")[:60])

    logger.info("=== DONE — #16 시각화: Aura 콘솔에서 MATCH (n:Entity) RETURN n LIMIT 50 ===")


if __name__ == "__main__":
    asyncio.run(main())
