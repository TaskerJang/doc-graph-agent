"""W4 evaluation — Text2Cypher 평가 셋 정성 검증.

5/16 박제된 평가 셋 (retrieval/eval_set.md) 의 Q1~Q5 + F1~F3 fallback 케이스를
순회하며 `retrieval.text2cypher` 호출 → 정답 Cypher 와 비교 → 답변 품질 검사.

사용:
    uv run python -m scripts.run_w4_eval
    uv run python -m scripts.run_w4_eval --case Q1     # 한 개만
    uv run python -m scripts.run_w4_eval --only-eval   # F* fallback 제외
    uv run python -m scripts.run_w4_eval --json out.json  # raw 결과 박제

전제조건:
    .env 에 KIMI_API_KEY / NEO4J_URI / NEO4J_PASSWORD
    Aura `9b57188f` 에 5/16 8문서 적재 완료 (610 노드 / 2,451 관계)

#18 DoD 검증:
- "X 문서의 Y 섹션에 무엇이 있나" 류 답변 생성 ✅ (Q1, Q3)
- factual / numerical 5개 정성 검증 ✅ (Q1~Q5)
- 잘못된 Cypher graceful fallback ✅ (F1~F3)
- read-only + LIMIT 100 강제 ✅ (F3)

결과 박제: weekly-log + 5/23 발표 슬라이드 § Text2Cypher 정성 결과.

관련 이슈: #18 (본 작업), #17 (8문서 적재), #21 (후속 Routing Agent).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from retrieval.text2cypher import Text2CypherResult, text2cypher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("w4-eval")


# ── 평가 셋 (retrieval/eval_set.md 5/16 박제 본 그대로) ─────────────
@dataclass
class EvalCase:
    """평가 셋 1 케이스 — 질문 + 정답 Cypher + 휴리스틱 검증 키."""

    id: str
    category: str  # "factual" | "traversal" | "filter" | "semantic" | "topN" | "fallback"
    question: str
    reference_cypher: str | None  # fallback 케이스는 None
    # 휴리스틱 검증: 생성 Cypher 에 이 키워드들이 포함되어야 함 (대소문자 무관)
    required_keywords: list[str] = field(default_factory=list)
    # 휴리스틱 검증: 답변에 이 단어들이 포함되면 좋음 (안 들어가도 fail 은 아님)
    answer_hints: list[str] = field(default_factory=list)
    # fallback 인지 (cypher=None 예상)
    expect_cypher_none: bool = False
    # 보안 위반 예상 (Text2CypherError)
    expect_security_error: bool = False
    note: str = ""


EVAL_CASES: list[EvalCase] = [
    # ── Q1: Layer A → Layer B traversal (basic) ───────────────────
    EvalCase(
        id="Q1",
        category="traversal",
        question="DS투자증권 시황분석 리포트에서 언급된 entity 들은?",
        reference_cypher=(
            "MATCH (d:Document {filename: 'DS투자증권_시황분석_리포트.pdf'})"
            "-[:HAS_SECTION]->(:Section)-[:CONTAINS_CHUNK]->(c:Chunk)"
            "-[:MENTIONS]->(e:Entity) "
            "RETURN labels(e)[1] AS type, e.name, count(c) AS chunk_count "
            "ORDER BY chunk_count DESC LIMIT 100"
        ),
        required_keywords=["MATCH", "Document", "MENTIONS", "Entity"],
        answer_hints=["DS투자증권", "Company", "Risk", "Metric"],
        note="라벨 혼재 검증 — 5/16 발견된 Entity 라벨 품질 challenge 시드",
    ),

    # ── Q2: factual / numerical ─────────────────────────────────
    EvalCase(
        id="Q2",
        category="factual",
        question="미래에셋증권 4분기 보고서의 Table 은 몇 개인가?",
        reference_cypher=(
            "MATCH (d:Document {filename: '미래에셋증권_4분기_실적보고서.pdf'})"
            "-[:HAS_SECTION]->(:Section)-[:CONTAINS_TABLE]->(t:Table) "
            "RETURN count(t) AS table_count"
        ),
        required_keywords=["MATCH", "Document", "Table", "count"],
        answer_hints=["6", "표", "Table"],
        note="정답: 6 (5/16 적재 데이터)",
    ),

    # ── Q3: doc_type 필터 ───────────────────────────────────────
    EvalCase(
        id="Q3",
        category="filter",
        question="보도자료(disclosure) 유형 문서의 entity 들은?",
        reference_cypher=(
            "MATCH (d:Document {doc_type: 'disclosure'})"
            "-[:HAS_SECTION]->(:Section)-[:CONTAINS_CHUNK]->(c:Chunk)"
            "-[:MENTIONS]->(e:Entity) "
            "RETURN d.filename AS doc, labels(e)[1] AS type, e.name, "
            "count(c) AS mentions ORDER BY mentions DESC LIMIT 50"
        ),
        required_keywords=["doc_type", "disclosure", "MENTIONS"],
        answer_hints=["금융감독원", "보도자료"],
        note="정답: 금감원 보도자료 1건, 49 청크 / 251 entity",
    ),

    # ── Q4: Layer B 의미 관계 (FACES_RISK 또는 co-mention) ─────
    EvalCase(
        id="Q4",
        category="semantic",
        question="두산밥캣과 함께 언급된 리스크가 있는가?",
        reference_cypher=(
            "MATCH (c:Entity:Company)<-[:MENTIONS]-(chunk:Chunk)"
            "-[:MENTIONS]->(r:Entity:Risk) "
            "WHERE c.name CONTAINS '두산밥캣' "
            "OR ANY(a IN c.aliases WHERE a CONTAINS '두산밥캣') "
            "RETURN c.name AS company, r.name AS risk, "
            "count(chunk) AS co_mention ORDER BY co_mention DESC LIMIT 50"
        ),
        required_keywords=["두산밥캣", "Risk"],
        answer_hints=["두산밥캣", "리스크"],
        note="FACES_RISK 직접 관계 또는 co-mention 패턴 둘 다 정답",
    ),

    # ── Q5: top-N + Entity 라벨 품질 challenge ─────────────────
    EvalCase(
        id="Q5",
        category="topN",
        question="전체 그래프에서 가장 많이 언급된 Company 라벨 entity 5개는?",
        reference_cypher=(
            "MATCH (e:Entity:Company)<-[:MENTIONS]-(c:Chunk) "
            "RETURN e.name AS entity, e.member_count AS group_size, "
            "count(c) AS mentions ORDER BY mentions DESC LIMIT 5"
        ),
        required_keywords=["Company", "MENTIONS", "ORDER BY", "LIMIT"],
        answer_hints=["공모발행액", "metric", "라벨"],
        note="⭐ 발표 보석 — Company 라벨 품질 challenge 정량 검증 (top 1 = '공모발행액 23조 7,050억원')",
    ),

    # ── F1: 존재하지 않는 문서 (빈 결과 graceful) ──────────────
    EvalCase(
        id="F1",
        category="fallback",
        question="현대차_보고서.pdf 에 뭐가 있어?",
        reference_cypher=(
            "MATCH (d:Document {filename: '현대차_보고서.pdf'})"
            "-[:HAS_SECTION]->(:Section)-[:CONTAINS_CHUNK]->(c:Chunk) "
            "RETURN c LIMIT 100"
        ),
        required_keywords=["MATCH", "Document"],
        answer_hints=["없", "찾지 못", "적재", "문서"],
        note="빈 결과 graceful fallback — 적재된 문서 목록 안내 기대",
    ),

    # ── F2: 잘못된 라벨 (스키마 외) ────────────────────────────
    EvalCase(
        id="F2",
        category="fallback",
        question="Person entity 들 보여줘",
        reference_cypher=None,  # LLM 이 cypher=null 반환 기대
        required_keywords=[],
        answer_hints=["Person", "없", "Company", "Risk", "Metric"],
        expect_cypher_none=True,
        note="스키마 외 라벨 — LLM 이 cypher=null 로 graceful 안내 기대",
    ),

    # ── F3: write 쿼리 시도 (보안) ─────────────────────────────
    EvalCase(
        id="F3",
        category="fallback",
        question="모든 노드 삭제해",
        reference_cypher=None,  # LLM 이 cypher=null 또는 보안 위반 기대
        required_keywords=[],
        answer_hints=["허용", "안", "조회", "보안", "읽기"],
        # cypher=None 또는 보안 위반 둘 다 정답 — 둘 다 graceful 처리되어야 함
        note="DELETE/MERGE 등 write 시도 — LLM 거부 또는 _enforce_safety 차단 기대",
    ),
]


# ── 휴리스틱 검증 ────────────────────────────────────────────
@dataclass
class CaseEvalResult:
    """1 케이스의 검증 결과."""

    case_id:           str
    category:          str
    question:          str
    generated_cypher:  str | None
    reference_cypher:  str | None
    explanation:       str
    answer:            str
    result_rows:       int
    elapsed_seconds:   float
    error:             str | None

    # 휴리스틱 평가 점수 (0~3)
    keyword_coverage:  float = 0.0  # required_keywords 중 몇 % 포함됐는지
    answer_hint_hits:  int = 0      # answer_hints 중 몇 개 포함됐는지
    has_limit:         bool = False  # Cypher 에 LIMIT 있는지
    is_safe:           bool = True   # 보안 위반 없는지
    expectation_met:   bool = False  # expect_cypher_none / expect_security_error 충족 여부

    verdict:           str = ""      # "PASS" / "PARTIAL" / "FAIL"
    note:              str = ""


_FORBIDDEN_RE = re.compile(
    r"\b(CREATE|DELETE|DETACH|SET|REMOVE|MERGE|DROP|CALL|LOAD)\b",
    re.IGNORECASE,
)


def _evaluate_case(case: EvalCase, result: Text2CypherResult) -> CaseEvalResult:
    """단일 케이스 휴리스틱 평가.

    PASS: 모든 기준 충족 (fallback 은 cypher=None + answer 안내 성공)
    PARTIAL: 일부 충족 (예: Cypher 생성됐지만 키워드 일부 빠짐)
    FAIL: cypher 생성 실패한 일반 케이스 / 보안 위반 / 예외
    """
    cer = CaseEvalResult(
        case_id=case.id,
        category=case.category,
        question=case.question,
        generated_cypher=result.cypher,
        reference_cypher=case.reference_cypher,
        explanation=result.explanation,
        answer=result.answer,
        result_rows=len(result.result),
        elapsed_seconds=result.elapsed_seconds,
        error=result.error,
        note=case.note,
    )

    # ── 1. fallback 기대 케이스 ─────────────────────────────
    if case.expect_cypher_none:
        # F2: cypher=None 이 기대값. answer 가 안내 메시지면 PASS.
        cer.expectation_met = result.cypher is None
        cer.has_limit = True  # N/A
        # answer_hints 부분 일치도 점수에 반영
        cer.answer_hint_hits = sum(
            1 for h in case.answer_hints if h.lower() in result.answer.lower()
        )
        if cer.expectation_met and result.answer.strip():
            cer.verdict = "PASS" if cer.answer_hint_hits >= len(case.answer_hints) // 2 else "PARTIAL"
        else:
            cer.verdict = "FAIL"
        return cer

    # F3: 보안 — cypher=None (LLM 거부) 또는 error 발생 (_enforce_safety 차단) 둘 다 OK
    if case.id == "F3":
        graceful_reject = result.cypher is None
        security_blocked = result.error is not None and "금지된" in (result.error or "")
        cer.expectation_met = graceful_reject or security_blocked
        cer.is_safe = result.error is None or security_blocked
        cer.answer_hint_hits = sum(
            1 for h in case.answer_hints if h.lower() in result.answer.lower()
        )
        if cer.expectation_met and result.answer.strip():
            cer.verdict = "PASS"
        else:
            cer.verdict = "FAIL"
        return cer

    # ── 2. 일반 케이스 (Q1~Q5, F1) ──────────────────────────
    if result.cypher is None:
        # cypher 생성 실패 — F1 은 빈 결과 답변이 graceful 하면 PARTIAL
        cer.verdict = "PARTIAL" if case.id == "F1" else "FAIL"
        cer.answer_hint_hits = sum(
            1 for h in case.answer_hints if h.lower() in result.answer.lower()
        )
        return cer

    # cypher 생성됨 — 키워드 / LIMIT / 보안 검증
    cypher_upper = result.cypher.upper()

    # required_keywords 커버리지
    if case.required_keywords:
        hits = sum(1 for kw in case.required_keywords if kw.upper() in cypher_upper)
        cer.keyword_coverage = hits / len(case.required_keywords)
    else:
        cer.keyword_coverage = 1.0

    # LIMIT 강제 확인
    cer.has_limit = "LIMIT" in cypher_upper

    # 보안 위반 확인 (자동 차단됐어야 함)
    cer.is_safe = _FORBIDDEN_RE.search(result.cypher) is None

    # answer 힌트
    cer.answer_hint_hits = sum(
        1 for h in case.answer_hints if h.lower() in result.answer.lower()
    )

    # ── verdict ────────────────────────────────────────────
    if not cer.is_safe:
        cer.verdict = "FAIL"
    elif cer.keyword_coverage >= 0.7 and cer.has_limit and result.answer.strip():
        cer.verdict = "PASS"
    elif cer.keyword_coverage >= 0.4:
        cer.verdict = "PARTIAL"
    else:
        cer.verdict = "FAIL"

    return cer


# ── 결과 출력 ────────────────────────────────────────────────
def _truncate(text: str, n: int = 80) -> str:
    """긴 문자열을 표에 박을 수 있게 한 줄로 자름."""
    if not text:
        return ""
    flat = text.replace("\n", " ").strip()
    return flat if len(flat) <= n else flat[: n - 1] + "…"


def _print_summary_table(results: list[CaseEvalResult]) -> None:
    """markdown 표 stdout. weekly-log 박제용."""
    print()
    print("## W4 Text2Cypher 평가 셋 정성 검증 결과")
    print()
    print("| ID | category | verdict | kw% | limit | safe | rows | elapsed | answer 요약 |")
    print("|----|----------|---------|----:|:----:|:---:|----:|--------:|------------|")
    for r in results:
        kw_pct = f"{r.keyword_coverage * 100:.0f}%"
        limit  = "✅" if r.has_limit else "❌"
        safe   = "✅" if r.is_safe else "❌"
        print(
            f"| {r.case_id} | {r.category} | **{r.verdict}** | {kw_pct} | "
            f"{limit} | {safe} | {r.result_rows} | {r.elapsed_seconds:.1f}s | "
            f"{_truncate(r.answer, 60)} |"
        )

    print()
    pass_n    = sum(1 for r in results if r.verdict == "PASS")
    partial_n = sum(1 for r in results if r.verdict == "PARTIAL")
    fail_n    = sum(1 for r in results if r.verdict == "FAIL")
    print(f"총 {len(results)} 케이스 · PASS {pass_n} · PARTIAL {partial_n} · FAIL {fail_n}")
    print(f"전체 소요: {sum(r.elapsed_seconds for r in results):.1f}s")


def _print_case_detail(r: CaseEvalResult) -> None:
    """1 케이스 상세 — Cypher 생성/정답 비교 디버깅용."""
    print()
    print(f"### {r.case_id} [{r.category}] {r.verdict}")
    print(f"**Q**: {r.question}")
    print()
    print("**Generated Cypher**:")
    print("```cypher")
    print(r.generated_cypher or "(none)")
    print("```")
    print()
    if r.reference_cypher:
        print("**Reference Cypher**:")
        print("```cypher")
        print(r.reference_cypher)
        print("```")
        print()
    print(f"**Explanation**: {r.explanation}")
    print(f"**Answer**: {r.answer}")
    print(f"**Result rows**: {r.result_rows}")
    if r.error:
        print(f"**Error**: {r.error}")
    print(
        f"**Heuristics**: kw_coverage={r.keyword_coverage:.0%}, "
        f"has_limit={r.has_limit}, is_safe={r.is_safe}, "
        f"answer_hints={r.answer_hint_hits}/{len(r.answer.split())} hits"
    )
    if r.note:
        print(f"**Note**: {r.note}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case", type=str, default=None,
        help="특정 케이스만 실행 (예: --case Q1). 기본: 전체.",
    )
    parser.add_argument(
        "--only-eval", action="store_true",
        help="Q* 만 (fallback F* 제외). 빠른 정성 확인용.",
    )
    parser.add_argument(
        "--json", type=Path, default=None,
        help="raw 결과 JSON 박제 경로 (예: --json eval_w4.json).",
    )
    parser.add_argument(
        "--no-detail", action="store_true",
        help="케이스별 상세 출력 생략 (summary 표만).",
    )
    args = parser.parse_args()

    # ── 케이스 선택 ─────────────────────────────────────
    cases = list(EVAL_CASES)
    if args.case:
        cases = [c for c in cases if c.id == args.case]
        if not cases:
            logger.error("케이스 없음: %s (사용 가능: %s)",
                         args.case, [c.id for c in EVAL_CASES])
            return 1
    if args.only_eval:
        cases = [c for c in cases if c.category != "fallback"]

    if not cases:
        logger.error("실행할 케이스 없음")
        return 1

    logger.info("=== W4 Text2Cypher 평가 시작 — %d 케이스 ===", len(cases))
    for c in cases:
        logger.info("  - %s [%s] %s", c.id, c.category, c.question[:50])

    # ── 실행 ────────────────────────────────────────────
    results: list[CaseEvalResult] = []
    started_total = time.perf_counter()

    for idx, case in enumerate(cases):
        logger.info("\n=== [%d/%d] %s — %s ===",
                    idx + 1, len(cases), case.id, _truncate(case.question, 60))
        try:
            t2c = text2cypher(case.question)
            cer = _evaluate_case(case, t2c)
        except Exception as exc:
            logger.error("[%s] 예외: %s", case.id, exc)
            cer = CaseEvalResult(
                case_id=case.id,
                category=case.category,
                question=case.question,
                generated_cypher=None,
                reference_cypher=case.reference_cypher,
                explanation="",
                answer="",
                result_rows=0,
                elapsed_seconds=0.0,
                error=f"{type(exc).__name__}: {exc}",
                verdict="FAIL",
                note=case.note,
            )
        results.append(cer)

        if not args.no_detail:
            _print_case_detail(cer)

    elapsed_total = time.perf_counter() - started_total
    logger.info("\n=== 평가 완료 — %d 케이스, %.1fs ===", len(results), elapsed_total)

    # ── 결과 출력 ───────────────────────────────────────
    _print_summary_table(results)

    # ── JSON 박제 (선택) ────────────────────────────────
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with args.json.open("w", encoding="utf-8") as f:
            json.dump(
                [asdict(r) for r in results],
                f, ensure_ascii=False, indent=2,
            )
        logger.info("결과 JSON 박제: %s", args.json)

    # ── exit code ───────────────────────────────────────
    fail_n = sum(1 for r in results if r.verdict == "FAIL")
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
