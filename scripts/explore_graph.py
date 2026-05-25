"""Graph 구조 탐색 자동화 — GraphRAG QA 40 작성 소스 데이터.

이 스크립트는 Neo4j Aura 에 적재된 그래프의 *현재 상태* 를 파악하는
6 개 사이퍼 쿼리를 자동 실행한다. 출력 JSON 은 GraphRAG QA 작성 시
정답의 ground truth 로 쓰인다.

## 실행

    # 전체 6 사이퍼 실행 + 콘솔 출력
    uv run python scripts/explore_graph.py

    # JSON 파일 저장 (GraphRAG QA 작성용)
    uv run python scripts/explore_graph.py --json eval/dataset/graph_meta.json

    # 특정 세그먼트만 실행
    uv run python scripts/explore_graph.py --section documents
    uv run python scripts/explore_graph.py --section entities
    uv run python scripts/explore_graph.py --section relations
    uv run python scripts/explore_graph.py --section top_entities
    uv run python scripts/explore_graph.py --section shared_entities
    uv run python scripts/explore_graph.py --section risk_company

## 전제조건

- .env 에 NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD 박혀있어야 함
- Neo4j Aura `9b57188f` (또는 동일 스키마) 에 5/16 8문서 적재 완료

## 사이퍼 쿼리 6 개

1. **documents** — 적재된 Document 목록 + 메타
2. **entities** — Entity 라벨 분포
3. **relations** — 관계 타입 분포
4. **top_entities** — 가장 많이 언급된 Entity TOP 20 (라벨별)
5. **shared_entities** — Document 간 공통 Entity
6. **risk_company** — Risk-Company 공동 언급 패턴
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("explore-graph")


# ============================================
# Cypher 사이퍼 쿼리 6 개
# ============================================

@dataclass
class ExploreQuery:
    name: str
    description: str
    cypher: str


EXPLORE_QUERIES: list[ExploreQuery] = [
    ExploreQuery(
        name="documents",
        description="적재된 Document 목록 + 메타 (어떤 문서가 있는지 파악)",
        cypher=(
            "MATCH (d:Document) "
            "RETURN d.filename AS filename, d.doc_type AS doc_type, "
            "       d.doc_year AS doc_year, d.page_count AS page_count "
            "ORDER BY d.filename"
        ),
    ),
    ExploreQuery(
        name="entities",
        description="Entity 라벨 분포 (Company / Risk / Metric / Recommendation / Outlook 은 몇 개씩?)",
        cypher=(
            "MATCH (e:Entity) "
            "WITH labels(e) AS lbls "
            "UNWIND lbls AS lbl "
            "WITH lbl WHERE lbl <> 'Entity' "
            "RETURN lbl AS label, count(*) AS count "
            "ORDER BY count DESC"
        ),
    ),
    ExploreQuery(
        name="relations",
        description="관계 타입 분포 (MENTIONS / CONTAINS_CHUNK / HAS_SECTION 수)",
        cypher=(
            "MATCH ()-[r]->() "
            "RETURN type(r) AS rel_type, count(*) AS count "
            "ORDER BY count DESC"
        ),
    ),
    ExploreQuery(
        name="top_entities",
        description="가장 많이 언급된 Entity TOP 20 (라벨별 — GraphRAG QA 작성 시드)",
        cypher=(
            "MATCH (e:Entity)<-[:MENTIONS]-(c:Chunk) "
            "WITH e, labels(e) AS lbls, count(c) AS mentions "
            "WHERE size(lbls) > 1 "
            "RETURN lbls[1] AS label, e.name AS entity, mentions "
            "ORDER BY mentions DESC LIMIT 20"
        ),
    ),
    ExploreQuery(
        name="shared_entities",
        description="Document 간 공통 Entity (교집합 QA 작성 시드)",
        cypher=(
            "MATCH (d1:Document)-[:HAS_SECTION]->(:Section)-[:CONTAINS_CHUNK]->"
            "(c1:Chunk)-[:MENTIONS]->(e:Entity) "
            "MATCH (d2:Document)-[:HAS_SECTION]->(:Section)-[:CONTAINS_CHUNK]->"
            "(c2:Chunk)-[:MENTIONS]->(e) "
            "WHERE d1.filename < d2.filename "
            "WITH d1.filename AS doc1, d2.filename AS doc2, "
            "     e.name AS entity, count(DISTINCT c1) + count(DISTINCT c2) AS shared "
            "WHERE shared > 5 "
            "RETURN doc1, doc2, entity, shared "
            "ORDER BY shared DESC LIMIT 20"
        ),
    ),
    ExploreQuery(
        name="risk_company",
        description="Risk-Company 공동 언급 패턴 (1-hop 관계 QA 작성 시드)",
        cypher=(
            "MATCH (c:Entity:Company)<-[:MENTIONS]-(chunk:Chunk)"
            "-[:MENTIONS]->(r:Entity:Risk) "
            "RETURN c.name AS company, r.name AS risk, "
            "       count(chunk) AS co_mention "
            "ORDER BY co_mention DESC LIMIT 20"
        ),
    ),
]


# ============================================
# 실행
# ============================================

def _get_driver():
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD")
    if not uri or not pwd:
        logger.error("NEO4J_URI / NEO4J_PASSWORD .env 미설정")
        sys.exit(1)
    return GraphDatabase.driver(uri, auth=(user, pwd))


def _run_query(driver, query: ExploreQuery) -> list[dict[str, Any]]:
    with driver.session() as session:
        result = session.run(query.cypher)
        return [dict(r) for r in result]


def _print_section(query: ExploreQuery, rows: list[dict[str, Any]]) -> None:
    print()
    print(f"## {query.name} — {query.description}")
    print()
    if not rows:
        print("  (결과 없음)")
        return
    keys = list(rows[0].keys())
    print("  | " + " | ".join(keys) + " |")
    print("  |" + "|".join(["---"] * len(keys)) + "|")
    for r in rows[:30]:
        cells = [str(r.get(k, ""))[:60] for k in keys]
        print("  | " + " | ".join(cells) + " |")
    if len(rows) > 30:
        print(f"  ... ({len(rows)} 총 행, 상위 30 만 표시)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--section", type=str, default=None,
        choices=[q.name for q in EXPLORE_QUERIES],
        help="특정 세그먼트만 실행. 기본: 전체",
    )
    parser.add_argument(
        "--json", type=Path, default=None,
        help="결과 JSON 파일 저장 경로 (GraphRAG QA 작성용)",
    )
    args = parser.parse_args()

    queries = EXPLORE_QUERIES
    if args.section:
        queries = [q for q in EXPLORE_QUERIES if q.name == args.section]

    logger.info("=== 그래프 탐색 시작 — %d 세그먼트 ===", len(queries))

    driver = _get_driver()
    output: dict[str, Any] = {}

    try:
        for q in queries:
            logger.info("실행: %s", q.name)
            rows = _run_query(driver, q)
            output[q.name] = {
                "description": q.description,
                "cypher": q.cypher,
                "row_count": len(rows),
                "rows": rows,
            }
            _print_section(q, rows)
    finally:
        driver.close()

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with args.json.open("w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info("결과 저장: %s", args.json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
