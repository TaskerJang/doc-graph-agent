"""P2 (#57) — Company→Metric 라벨 교정 마이그레이션.

배경: W3 측정에서 doc-graph(GraphRAG)가 BM25 baseline 에 전 영역 패배.
원인 진단 — Router→LocalRetriever 경로인데 LocalRetriever 매칭 0개. 근본
원인은 추출기(kg/extractor.py)가 재무 지표(영업이익/OPM/목표주가 등)를
:Company 로 오라벨해 Company 라벨 공간이 오염된 것 (#57, docs/before-after.md #2/#6).

본 스크립트는 재인제스트 없이 기존 Neo4j 그래프를 Cypher 로 교정한다:
    (:Entity:Company {entity_type:'Company'}) → (:Entity:Metric {entity_type:'Metric'})

안전장치:
- 기본 dry-run. 실제 write 는 --apply 필요.
- --diagnose: 전체 :Company 노드를 먼저 사람이 검토 (어떤 게 진짜 회사이고
  어떤 게 지표인지, 두산밥캣 같은 실제 회사가 노드로 존재하는지 확인).
- 대상 선택: --group-ids 명시 리스트(정밀) 또는 이름 휴리스틱(_looks_like_metric).

진단 모드 (모두 read-only):
- --docs          : 그래프에 적재된 Document 목록 (QA 대상 문서가 들어있는지)
- --label-dist    : entity_type 분포 (노이즈 규모)
- --find STR      : 이름에 STR 포함된 Entity 를 라벨 무관 검색 (두산밥캣 존재/라벨)
- --chunk-find STR: 청크 텍스트에 STR 포함 검색 (파싱 vs 추출 프롬프트 판별)

검증: 교정 후 #61 동일 80 QA 재측정 → before/after.

사용:
    uv run python scripts/migrate_relabel_metric.py --diagnose
    uv run python scripts/migrate_relabel_metric.py --docs
    uv run python scripts/migrate_relabel_metric.py --find 두산
    uv run python scripts/migrate_relabel_metric.py --chunk-find 두산
    uv run python scripts/migrate_relabel_metric.py                       # dry-run (휴리스틱)
    uv run python scripts/migrate_relabel_metric.py --group-ids g1,g2     # dry-run (명시)
    uv run python scripts/migrate_relabel_metric.py --group-ids g1,g2 --apply
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

# repo 루트를 path 에 추가 — `uv run python scripts/...` 로 직접 실행 시에도
# kg 패키지를 import 할 수 있게 한다 (run_qa_eval.py 와 동일 패턴).
sys.path.insert(0, str(Path(__file__).parent.parent))

from kg.neo4j_client import Neo4jClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ── 지표성 이름 휴리스틱 ───────────────────────────────────
# 숫자 · 통화/비율 단위 · 대표 지표 키워드 중 하나라도 있으면 '지표로 의심'.
# 어디까지나 휴리스틱이므로 반드시 --diagnose / dry-run 으로 사람이 검토 후 --apply.
_METRIC_UNIT_RE = re.compile(r"[%％]|\d|원|조|억|배|%p|bp|pt|달러|USD")
_METRIC_KEYWORDS = (
    "영업이익", "영업이익률", "매출", "순이익", "이익", "마진", "EPS", "PER",
    "PBR", "ROE", "ROA", "OPM", "EBITDA", "성장률", "수익률", "배당", "현금흐름",
    "부채비율", "점유율", "가동률", "재고", "수주", "목표주가", "주가",
)


def _looks_like_metric(name: str | None) -> bool:
    """이름만 보고 '지표일 가능성' 판단 (휴리스틱)."""
    if not name:
        return False
    if _METRIC_UNIT_RE.search(name):
        return True
    return any(kw in name for kw in _METRIC_KEYWORDS)


# ── Cypher ────────────────────────────────────────────────
# ORDER BY ... LIMIT 을 한 줄에 둬서 Neo4jClient._ensure_limit 의 " LIMIT " 감지에
# 걸리게 한다 (이중 LIMIT 부착 방지).
_DIAGNOSE = """
MATCH (e:Entity:Company)
OPTIONAL MATCH (e)-[r]-()
RETURN e.group_id AS group_id, e.name AS name,
       e.member_count AS members, count(r) AS degree
ORDER BY name LIMIT 1000
""".strip()

_RELABEL = """
MATCH (e:Entity:Company)
WHERE e.group_id IN $gids
REMOVE e:Company
SET e:Metric,
    e.entity_type  = 'Metric',
    e.relabeled_at = timestamp(),
    e.relabel_note = 'P2 #57 Company->Metric'
RETURN e.group_id AS group_id, e.name AS name
""".strip()

# ── 진단용 (변경 없음, read-only) ─────────────────────────
_DOCS = """
MATCH (d:Document)
RETURN d.filename AS doc, d.fiscal_year AS fiscal_year
ORDER BY doc LIMIT 1000
""".strip()

_LABEL_DIST = """
MATCH (e:Entity)
RETURN e.entity_type AS type, count(*) AS n
ORDER BY n DESC LIMIT 1000
""".strip()

_FIND = """
MATCH (e:Entity)
WHERE e.name CONTAINS $q
RETURN labels(e) AS labels, e.name AS name, e.entity_type AS type
ORDER BY name LIMIT 1000
""".strip()

_CHUNK_FIND = """
MATCH (c:Chunk)
WHERE c.text CONTAINS $q
RETURN c.id AS id, substring(c.text, 0, 240) AS preview
ORDER BY id LIMIT 20
""".strip()


def _fetch_companies(client: Neo4jClient) -> list[dict]:
    return client.read(_DIAGNOSE)


def diagnose(client: Neo4jClient) -> None:
    rows = _fetch_companies(client)
    logger.info("== :Company 노드 %d개 ==", len(rows))
    for r in rows:
        flag = "  <-- METRIC 의심" if _looks_like_metric(r.get("name")) else ""
        logger.info(
            "  %-40s members=%-3s degree=%-3s%s",
            r.get("name"), r.get("members"), r.get("degree"), flag,
        )
    suspects = [r for r in rows if _looks_like_metric(r.get("name"))]
    logger.info("휴리스틱상 지표 의심: %d / %d", len(suspects), len(rows))
    logger.info("group_id 목록(의심): %s", ",".join(r["group_id"] for r in suspects))


def list_docs(client: Neo4jClient) -> None:
    """그래프에 실제 적재된 Document 목록 — QA 대상 문서가 들어있는지 확인."""
    rows = client.read(_DOCS)
    logger.info("== 그래프 적재 Document %d개 ==", len(rows))
    for r in rows:
        logger.info("  %-50s fy=%s", r.get("doc"), r.get("fiscal_year"))


def label_dist(client: Neo4jClient) -> None:
    """entity_type 분포 — 노이즈 규모 파악."""
    rows = client.read(_LABEL_DIST)
    logger.info("== Entity 타입 분포 ==")
    for r in rows:
        logger.info("  %-16s %s", r.get("type"), r.get("n"))


def find_entity(client: Neo4jClient, q: str) -> None:
    """이름에 q 가 포함된 Entity 를 라벨 무관하게 검색 (두산밥캣 존재/라벨 확인)."""
    rows = client.read(_FIND, q=q)
    logger.info("== '%s' 포함 Entity %d개 ==", q, len(rows))
    for r in rows:
        logger.info("  %-30s labels=%s type=%s", r.get("name"), r.get("labels"), r.get("type"))


def chunk_find(client: Neo4jClient, q: str) -> None:
    """청크 텍스트에 q 가 들어있나 — 파싱(B1) vs 추출프롬프트(B2) 판별.

    청크에 q 가 멀쩡히 있는데 Entity 가 없으면 → 추출 프롬프트 문제 (P1).
    청크에도 q 가 없거나 깨져 있으면 → 파싱/OCR 문제 (VLM, P3).
    """
    rows = client.read(_CHUNK_FIND, q=q)
    logger.info("== 텍스트에 '%s' 포함 Chunk %d개 ==", q, len(rows))
    for r in rows:
        logger.info("  [%s] %s", r.get("id"), r.get("preview"))


def select_targets(client: Neo4jClient, explicit: list[str] | None) -> list[dict]:
    rows = _fetch_companies(client)
    if explicit:
        wanted = set(explicit)
        return [r for r in rows if r.get("group_id") in wanted]
    return [r for r in rows if _looks_like_metric(r.get("name"))]


def main() -> None:
    ap = argparse.ArgumentParser(description="P2 #57 — Company->Metric 라벨 교정")
    ap.add_argument("--diagnose", action="store_true",
                    help="전체 :Company 노드 출력 후 종료 (변경 없음)")
    ap.add_argument("--docs", action="store_true",
                    help="그래프 적재 Document 목록 출력 후 종료 (변경 없음)")
    ap.add_argument("--label-dist", action="store_true",
                    help="Entity 타입 분포 출력 후 종료 (변경 없음)")
    ap.add_argument("--find", default="",
                    help="이름에 문자열 포함된 Entity 를 라벨 무관 검색 후 종료")
    ap.add_argument("--chunk-find", default="",
                    help="청크 텍스트에 문자열 포함된 Chunk 검색 후 종료 (파싱 vs 추출 판별)")
    ap.add_argument("--group-ids", default="",
                    help="교정 대상 group_id 콤마구분 (명시 선택). 미지정 시 이름 휴리스틱")
    ap.add_argument("--apply", action="store_true",
                    help="실제 적용. 없으면 dry-run")
    args = ap.parse_args()

    explicit = [g.strip() for g in args.group_ids.split(",") if g.strip()] or None

    with Neo4jClient() as client:
        if args.docs:
            list_docs(client)
            return
        if args.label_dist:
            label_dist(client)
            return
        if args.find:
            find_entity(client, args.find)
            return
        if args.chunk_find:
            chunk_find(client, args.chunk_find)
            return
        if args.diagnose:
            diagnose(client)
            return

        targets = select_targets(client, explicit)
        mode = "명시 리스트" if explicit else "이름 휴리스틱"
        logger.info("== 대상 선택 (%s): %d개 ==", mode, len(targets))
        for r in targets:
            logger.info("  %-40s (%s)", r.get("name"), r.get("group_id"))

        if not targets:
            logger.info("대상 없음 — 종료")
            return

        if not args.apply:
            logger.info("DRY-RUN — 실제 변경 없음. 적용하려면 --apply 추가")
            return

        gids = [r["group_id"] for r in targets]
        changed = client.write(_RELABEL, gids=gids)
        logger.info("== 적용 완료: %d개 Company -> Metric ==", len(changed))
        for r in changed:
            logger.info("  OK  %s", r.get("name"))


if __name__ == "__main__":
    main()
