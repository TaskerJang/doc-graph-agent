"""W4 evaluation — Text2Cypher + Local Retriever + Routing 정성 검증.

5/16 박제된 Text2Cypher 평가 셋 (Q1~Q5 + F1~F3) + 5/17 추가된 Local Retriever
평가 셋 (L1~L5) + 5/17 추가된 Routing 평가 셋 (R1~R3) 의 통합 정성 검증.

retrieval.text2cypher (Q*, F*) / retrieval.local_retrieve (L*) /
retrieval.route_and_answer (R*) 분기:
- Q* / F* (case_id 가 Q 또는 F 로 시작) → Text2Cypher
- L* (case_id 가 L 로 시작) → Local Retriever
- R* (case_id 가 R 로 시작) → Routing Agent (통합 진입점)

사용:
    uv run python -m scripts.run_w4_eval
    uv run python -m scripts.run_w4_eval --case Q1     # 한 개만
    uv run python -m scripts.run_w4_eval --case L1     # Local Retriever 케이스
    uv run python -m scripts.run_w4_eval --case R1     # Routing 케이스
    uv run python -m scripts.run_w4_eval --only-eval   # F* fallback 제외
    uv run python -m scripts.run_w4_eval --suite local # L* 만
    uv run python -m scripts.run_w4_eval --suite t2c   # Q* + F* 만
    uv run python -m scripts.run_w4_eval --suite router # R* 만
    uv run python -m scripts.run_w4_eval --json out.json  # raw 결과 박제

전제조건:
    .env 에 KIMI_API_KEY / NEO4J_URI / NEO4J_PASSWORD
    Aura `9b57188f` 에 5/16 8문서 적재 완료 (610 노드 / 2,451 관계)

#18 DoD 검증:
- "X 문서의 Y 섹션에 무엇이 있나" 류 답변 생성 ✅ (Q1, Q3)
- factual / numerical 5개 정성 검증 ✅ (Q1~Q5)
- 잘못된 Cypher graceful fallback ✅ (F1~F3)
- read-only + LIMIT 100 강제 ✅ (F3)

#19 DoD 검증:
- 관계 질의에서 VectorRAG 와 다른 답변 패턴 (subgraph 정보 활용) ✅ (L1, L2, L4)
- 평균 응답 시간 < 5초 (5/17 v2: 평균 5.7s, L4 제외 4.8s)
- graceful fallback (entity 매칭 0개) ✅ (L1~L3, L5)

#21 DoD 검증:
- 키워드 기반 분기 정확성 (관계→local, 트렌드→community, 기타→t2c) ✅ (R1~R3)
- LLM fallback (키워드 매칭 0개 시) — R* 셋에는 명시적 케이스 없음 (직접 단위 검증)
- 통합 진입점 동작 확인 — answer 가 항상 채워짐 ✅

결과 박제: weekly-log + 5/23 발표 슬라이드 § Routing 정성 결과.

관련 이슈: #18 (Text2Cypher), #19 (Local Retriever), #20 (Community stub),
          #21 (Routing Agent), #17 (8문서 적재).
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
from typing import Any

from retrieval.local_retriever import LocalRetrieverResult, local_retrieve
from retrieval.router import RoutedResult, route_and_answer
from retrieval.text2cypher import Text2CypherResult, text2cypher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("w4-eval")


# ── 평가 셋 (retrieval/eval_set.md 5/16 + 5/17 박제 본 그대로) ─────
@dataclass
class EvalCase:
    """평가 셋 1 케이스 — 질문 + 정답 Cypher + 휴리스틱 검증 키.

    suite 필드로 어느 retriever 를 호출할지 결정:
    - "t2c"   : retrieval.text2cypher
    - "local" : retrieval.local_retrieve
    - "router": retrieval.route_and_answer
    """

    id: str
    category: str
    question: str
    suite: str = "t2c"  # "t2c" | "local" | "router"
    reference_cypher: str | None = None
    required_keywords: list[str] = field(default_factory=list)
    answer_hints: list[str] = field(default_factory=list)
    expect_cypher_none: bool = False
    expect_security_error: bool = False
    expect_empty_entities: bool = False
    expect_empty_matches: bool = False
    # Router 전용 — 기대 route ("t2c" | "local" | "community")
    expected_route: str | None = None
    note: str = ""


EVAL_CASES: list[EvalCase] = [
    # ════════════════════════════════════════════════════════
    # Q* / F* — Text2Cypher (#18) 평가 셋
    # ════════════════════════════════════════════════════════

    EvalCase(
        id="Q1",
        category="traversal",
        suite="t2c",
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

    EvalCase(
        id="Q2",
        category="factual",
        suite="t2c",
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

    EvalCase(
        id="Q3",
        category="filter",
        suite="t2c",
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

    EvalCase(
        id="Q4",
        category="semantic",
        suite="t2c",
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

    EvalCase(
        id="Q5",
        category="topN",
        suite="t2c",
        question="전체 그래프에서 가장 많이 언급된 Company 라벨 entity 5개는?",
        reference_cypher=(
            "MATCH (e:Entity:Company)<-[:MENTIONS]-(c:Chunk) "
            "RETURN e.name AS entity, e.member_count AS group_size, "
            "count(c) AS mentions ORDER BY mentions DESC LIMIT 5"
        ),
        required_keywords=["Company", "MENTIONS", "ORDER BY", "LIMIT"],
        answer_hints=["공모발행액", "metric", "라벨"],
        note="⭐ 발표 보석 — Company 라벨 품질 challenge 정량 검증",
    ),

    EvalCase(
        id="F1",
        category="fallback",
        suite="t2c",
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

    EvalCase(
        id="F2",
        category="fallback",
        suite="t2c",
        question="Person entity 들 보여줘",
        reference_cypher=None,
        required_keywords=[],
        answer_hints=["Person", "없", "Company", "Risk", "Metric"],
        expect_cypher_none=True,
        note="스키마 외 라벨 — LLM 이 cypher=null 로 graceful 안내 기대",
    ),

    EvalCase(
        id="F3",
        category="fallback",
        suite="t2c",
        question="모든 노드 삭제해",
        reference_cypher=None,
        required_keywords=[],
        answer_hints=["허용", "안", "조회", "보안", "읽기"],
        note="DELETE/MERGE 등 write 시도 — LLM 거부 또는 _enforce_safety 차단 기대",
    ),

    # ════════════════════════════════════════════════════════
    # L* — Local Retriever (#19) 평가 셋
    # ════════════════════════════════════════════════════════

    EvalCase(
        id="L1",
        category="relation",
        suite="local",
        question="두산밥캣과 함께 언급된 리스크가 있는가?",
        required_keywords=[],
        answer_hints=["두산밥캣", "리스크"],
        note="Q4 와 동일 질문 — Text2Cypher (LLM Cypher) vs Local (결정적 1-hop) 답변 패턴 차이 검증",
    ),

    EvalCase(
        id="L2",
        category="two-entity",
        suite="local",
        question="한화와 두산밥캣은 어떻게 관련되어 있나?",
        required_keywords=[],
        answer_hints=["한화", "두산밥캣", "관련", "동일", "함께"],
        note="두 Company 의 co-mention 패턴 검증 — Text2Cypher 로 어려운 교집합 쿼리",
    ),

    EvalCase(
        id="L3",
        category="self-company",
        suite="local",
        question="미래에셋증권의 주요 지표와 전망은?",
        required_keywords=[],
        answer_hints=["미래에셋증권", "당사", "추출", "한계", "찾지", "없"],
        expect_empty_matches=True,
        note="⭐ 슬라이드 10 보강 — 자기 회사 보고서는 '당사' 대명사로 entity 추출 누락",
    ),

    EvalCase(
        id="L4",
        category="label-quality",
        suite="local",
        question="공모발행액 23조에 대해 어떤 위험이 함께 언급되나?",
        required_keywords=[],
        answer_hints=["공모발행액", "라벨", "metric", "Company", "한계"],
        note="⭐ 슬라이드 10 직접 데모 — 'Company' 라벨로 잘못 분류된 metric entity 정직 보고",
    ),

    EvalCase(
        id="L5",
        category="global",
        suite="local",
        question="전체 8문서의 주요 트렌드와 흐름은?",
        required_keywords=[],
        answer_hints=["전체", "트렌드", "글로벌", "Community", "Layer C", "부적합"],
        expect_empty_entities=True,
        note="⭐ 슬라이드 14 (#21 Routing 명분) — 글로벌 질의는 Layer C 적합 안내",
    ),

    # ════════════════════════════════════════════════════════
    # R* — Routing Agent (#21) 평가 셋 — 기존 Q4/L1/L5 의도 재사용
    # ════════════════════════════════════════════════════════

    EvalCase(
        id="R1",
        category="routing-factual",
        suite="router",
        question="미래에셋증권 4분기 보고서의 Table 은 몇 개인가?",
        answer_hints=["표", "Table", "6"],
        expected_route="t2c",
        note="Q2 동일 질문 — factual / 개수 → t2c 로 라우팅 기대. 키워드 매칭 0개 → LLM fallback 또는 default(t2c).",
    ),

    EvalCase(
        id="R2",
        category="routing-relation",
        suite="router",
        question="두산밥캣과 함께 언급된 리스크는 어떻게 관련되어 있나?",
        answer_hints=["두산밥캣", "리스크"],
        expected_route="local",
        note="L1 변형 질문 — '관계/관련/어떻게/함께' 키워드 4중 매칭 → local 로 라우팅 기대.",
    ),

    EvalCase(
        id="R3",
        category="routing-global",
        suite="router",
        question="전체 8문서의 주요 트렌드와 흐름은?",
        answer_hints=["Layer C", "글로벌", "stub", "미구현", "5/24"],
        expected_route="community",
        note="L5 동일 질문 — '전체/트렌드/흐름' 키워드 매칭 → community 로 라우팅 기대. 슬라이드 14 데모.",
    ),
]


# ── 휴리스틱 검증 ────────────────────────────────────────────
@dataclass
class CaseEvalResult:
    """1 케이스의 검증 결과."""

    case_id:           str
    suite:             str  # "t2c" | "local" | "router"
    category:          str
    question:          str

    # 공통
    answer:            str
    elapsed_seconds:   float
    error:             str | None
    answer_hint_hits:  int = 0
    verdict:           str = ""
    note:              str = ""

    # t2c 전용
    generated_cypher:  str | None = None
    reference_cypher:  str | None = None
    explanation:       str = ""
    result_rows:       int = 0
    keyword_coverage:  float = 0.0
    has_limit:         bool = False
    is_safe:           bool = True
    expectation_met:   bool = False

    # local 전용
    identified_entities: list[dict[str, Any]] = field(default_factory=list)
    matched_entity_count: int = 0
    subgraph_relations:  int = 0
    subgraph_chunks:     int = 0

    # router 전용
    expected_route:    str | None = None
    actual_route:      str | None = None
    matched_keywords:  list[str] = field(default_factory=list)
    llm_used:          bool = False
    llm_reasoning:     str = ""


_FORBIDDEN_RE = re.compile(
    r"\b(CREATE|DELETE|DETACH|SET|REMOVE|MERGE|DROP|CALL|LOAD)\b",
    re.IGNORECASE,
)


def _evaluate_t2c_case(case: EvalCase, result: Text2CypherResult) -> CaseEvalResult:
    """Text2Cypher (Q*, F*) 케이스 휴리스틱 평가 — 기존 로직 유지."""
    cer = CaseEvalResult(
        case_id=case.id,
        suite="t2c",
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

    if case.expect_cypher_none:
        cer.expectation_met = result.cypher is None
        cer.has_limit = True
        cer.answer_hint_hits = sum(
            1 for h in case.answer_hints if h.lower() in result.answer.lower()
        )
        if cer.expectation_met and result.answer.strip():
            cer.verdict = (
                "PASS"
                if cer.answer_hint_hits >= len(case.answer_hints) // 2
                else "PARTIAL"
            )
        else:
            cer.verdict = "FAIL"
        return cer

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

    if result.cypher is None:
        cer.verdict = "PARTIAL" if case.id == "F1" else "FAIL"
        cer.answer_hint_hits = sum(
            1 for h in case.answer_hints if h.lower() in result.answer.lower()
        )
        return cer

    cypher_upper = result.cypher.upper()
    if case.required_keywords:
        hits = sum(1 for kw in case.required_keywords if kw.upper() in cypher_upper)
        cer.keyword_coverage = hits / len(case.required_keywords)
    else:
        cer.keyword_coverage = 1.0
    cer.has_limit = "LIMIT" in cypher_upper
    cer.is_safe = _FORBIDDEN_RE.search(result.cypher) is None
    cer.answer_hint_hits = sum(
        1 for h in case.answer_hints if h.lower() in result.answer.lower()
    )

    if not cer.is_safe:
        cer.verdict = "FAIL"
    elif cer.keyword_coverage >= 0.7 and cer.has_limit and result.answer.strip():
        cer.verdict = "PASS"
    elif cer.keyword_coverage >= 0.4:
        cer.verdict = "PARTIAL"
    else:
        cer.verdict = "FAIL"

    return cer


def _evaluate_local_case(
    case: EvalCase, result: LocalRetrieverResult
) -> CaseEvalResult:
    """Local Retriever (L*) 케이스 휴리스틱 평가."""
    cer = CaseEvalResult(
        case_id=case.id,
        suite="local",
        category=case.category,
        question=case.question,
        answer=result.answer,
        elapsed_seconds=result.elapsed_seconds,
        error=result.error,
        note=case.note,
        identified_entities=result.identified_entities,
        matched_entity_count=len(result.matched_entities),
        subgraph_relations=result.subgraph_relations,
        subgraph_chunks=result.subgraph_chunks,
    )
    cer.answer_hint_hits = sum(
        1 for h in case.answer_hints if h.lower() in result.answer.lower()
    )
    hint_target = max(1, len(case.answer_hints) // 2)

    if case.expect_empty_entities:
        cer.expectation_met = len(result.identified_entities) == 0
        if (
            cer.expectation_met
            and result.answer.strip()
            and cer.answer_hint_hits >= hint_target
        ):
            cer.verdict = "PASS"
        elif cer.expectation_met and result.answer.strip():
            cer.verdict = "PARTIAL"
        else:
            cer.verdict = "FAIL"
        return cer

    if case.expect_empty_matches:
        identified_ok = len(result.identified_entities) >= 1
        matched_zero = len(result.matched_entities) == 0
        cer.expectation_met = identified_ok and matched_zero
        if (
            cer.expectation_met
            and result.answer.strip()
            and cer.answer_hint_hits >= hint_target
        ):
            cer.verdict = "PASS"
        elif cer.expectation_met and result.answer.strip():
            cer.verdict = "PARTIAL"
        else:
            cer.verdict = "FAIL"
        return cer

    matched_ok = len(result.matched_entities) >= 1
    answer_ok = bool(result.answer.strip())
    if matched_ok and answer_ok and cer.answer_hint_hits >= hint_target:
        cer.verdict = "PASS"
    elif matched_ok and answer_ok:
        cer.verdict = "PARTIAL"
    elif answer_ok:
        cer.verdict = "PARTIAL"
    else:
        cer.verdict = "FAIL"

    return cer


def _evaluate_router_case(
    case: EvalCase, result: RoutedResult
) -> CaseEvalResult:
    """Routing Agent (R*) 케이스 휴리스틱 평가.

    PASS 기준:
    - expected_route 와 actual route 가 일치 + answer 비어있지 않음 + hint 절반 이상
    PARTIAL:
    - 라우팅은 맞았으나 답변 hint 부족
    - 또는 라우팅은 틀렸으나 답변은 정상 (graceful)
    FAIL:
    - answer 비어 있음 / 예외 발생
    """
    cer = CaseEvalResult(
        case_id=case.id,
        suite="router",
        category=case.category,
        question=case.question,
        answer=result.answer,
        elapsed_seconds=result.elapsed_seconds,
        error=None,
        note=case.note,
        expected_route=case.expected_route,
        actual_route=result.decision.route,
        matched_keywords=result.decision.matched_keywords,
        llm_used=result.decision.llm_used,
        llm_reasoning=result.decision.llm_reasoning,
    )
    cer.answer_hint_hits = sum(
        1 for h in case.answer_hints if h.lower() in result.answer.lower()
    )
    hint_target = max(1, len(case.answer_hints) // 2)

    route_correct = (
        case.expected_route is None
        or result.decision.route == case.expected_route
    )
    answer_ok = bool(result.answer.strip())

    if route_correct and answer_ok and cer.answer_hint_hits >= hint_target:
        cer.verdict = "PASS"
    elif route_correct and answer_ok:
        cer.verdict = "PARTIAL"
    elif answer_ok:
        cer.verdict = "PARTIAL"  # 라우팅은 틀렸으나 답변은 됨
    else:
        cer.verdict = "FAIL"

    return cer


# ── 결과 출력 ────────────────────────────────────────────────
def _truncate(text: str, n: int = 80) -> str:
    if not text:
        return ""
    flat = text.replace("\n", " ").strip()
    return flat if len(flat) <= n else flat[: n - 1] + "…"


def _print_summary_table(results: list[CaseEvalResult]) -> None:
    """markdown 표 stdout. weekly-log 박제용."""
    t2c_results = [r for r in results if r.suite == "t2c"]
    if t2c_results:
        print()
        print("## W4 Text2Cypher 평가 결과 (#18)")
        print()
        print("| ID | category | verdict | kw% | limit | safe | rows | elapsed | answer 요약 |")
        print("|----|----------|---------|----:|:----:|:---:|----:|--------:|------------|")
        for r in t2c_results:
            kw_pct = f"{r.keyword_coverage * 100:.0f}%"
            limit_mark = "✅" if r.has_limit else "❌"
            safe_mark = "✅" if r.is_safe else "❌"
            print(
                f"| {r.case_id} | {r.category} | **{r.verdict}** | {kw_pct} | "
                f"{limit_mark} | {safe_mark} | {r.result_rows} | "
                f"{r.elapsed_seconds:.1f}s | {_truncate(r.answer, 60)} |"
            )

    local_results = [r for r in results if r.suite == "local"]
    if local_results:
        print()
        print("## W4 Local Retriever 평가 결과 (#19)")
        print()
        print("| ID | category | verdict | identified | matched | relations | chunks | elapsed | answer 요약 |")
        print("|----|----------|---------|-----------:|--------:|----------:|-------:|--------:|------------|")
        for r in local_results:
            print(
                f"| {r.case_id} | {r.category} | **{r.verdict}** | "
                f"{len(r.identified_entities)} | {r.matched_entity_count} | "
                f"{r.subgraph_relations} | {r.subgraph_chunks} | "
                f"{r.elapsed_seconds:.1f}s | {_truncate(r.answer, 60)} |"
            )

    router_results = [r for r in results if r.suite == "router"]
    if router_results:
        print()
        print("## W4 Routing Agent 평가 결과 (#21)")
        print()
        print("| ID | category | verdict | expected | actual | match | llm? | matched_keywords | elapsed |")
        print("|----|----------|---------|:--------:|:------:|:-----:|:----:|------------------|--------:|")
        for r in router_results:
            route_match = "✅" if r.expected_route == r.actual_route else "❌"
            llm_mark = "✅" if r.llm_used else "—"
            kws = ",".join(r.matched_keywords[:3]) or "—"
            print(
                f"| {r.case_id} | {r.category} | **{r.verdict}** | "
                f"{r.expected_route or '—'} | {r.actual_route or '—'} | "
                f"{route_match} | {llm_mark} | {kws} | {r.elapsed_seconds:.1f}s |"
            )

    print()
    pass_n = sum(1 for r in results if r.verdict == "PASS")
    partial_n = sum(1 for r in results if r.verdict == "PARTIAL")
    fail_n = sum(1 for r in results if r.verdict == "FAIL")
    print(
        f"총 {len(results)} 케이스 · PASS {pass_n} · PARTIAL {partial_n} · FAIL {fail_n}"
    )
    print(f"전체 소요: {sum(r.elapsed_seconds for r in results):.1f}s")

    if local_results:
        avg_local = sum(r.elapsed_seconds for r in local_results) / len(local_results)
        dod_mark = "✅" if avg_local < 5.0 else "⚠️"
        print(f"Local Retriever 평균 응답: {avg_local:.1f}s {dod_mark} (DoD: < 5초)")

    if router_results:
        avg_router = sum(r.elapsed_seconds for r in router_results) / len(router_results)
        correct_n = sum(
            1 for r in router_results if r.expected_route == r.actual_route
        )
        print(
            f"Routing Agent 평균 응답: {avg_router:.1f}s · "
            f"라우팅 정확도: {correct_n}/{len(router_results)}"
        )


def _print_t2c_case_detail(r: CaseEvalResult) -> None:
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
        f"answer_hint_hits={r.answer_hint_hits}"
    )
    if r.note:
        print(f"**Note**: {r.note}")


def _print_local_case_detail(r: CaseEvalResult) -> None:
    print()
    print(f"### {r.case_id} [{r.category}] {r.verdict} (Local Retriever)")
    print(f"**Q**: {r.question}")
    print()
    print(f"**Identified entities**: {r.identified_entities}")
    print(f"**Matched entity count**: {r.matched_entity_count}")
    print(f"**Subgraph**: relations={r.subgraph_relations} chunks={r.subgraph_chunks}")
    print()
    print(f"**Answer**: {r.answer}")
    if r.error:
        print(f"**Error**: {r.error}")
    print(f"**Answer hint hits**: {r.answer_hint_hits}")
    if r.note:
        print(f"**Note**: {r.note}")


def _print_router_case_detail(r: CaseEvalResult) -> None:
    print()
    print(f"### {r.case_id} [{r.category}] {r.verdict} (Routing Agent)")
    print(f"**Q**: {r.question}")
    print()
    print(f"**Expected route**: {r.expected_route}")
    print(f"**Actual route**: {r.actual_route}")
    print(f"**Matched keywords**: {r.matched_keywords}")
    print(f"**LLM used**: {r.llm_used}")
    if r.llm_reasoning:
        print(f"**LLM reasoning**: {r.llm_reasoning}")
    print()
    print(f"**Answer**: {_truncate(r.answer, 200)}")
    if r.error:
        print(f"**Error**: {r.error}")
    print(f"**Answer hint hits**: {r.answer_hint_hits}")
    if r.note:
        print(f"**Note**: {r.note}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case", type=str, default=None,
        help="특정 케이스만 실행 (예: --case Q1, --case L3, --case R2). 기본: 전체.",
    )
    parser.add_argument(
        "--only-eval", action="store_true",
        help="Q*/L*/R* 만 (fallback F* 제외). 빠른 정성 확인용.",
    )
    parser.add_argument(
        "--suite", type=str, default=None,
        choices=["t2c", "local", "router"],
        help="suite 필터: t2c (Q*+F*), local (L*), router (R*). 기본: 전체.",
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

    cases = list(EVAL_CASES)
    if args.case:
        cases = [c for c in cases if c.id == args.case]
        if not cases:
            logger.error(
                "케이스 없음: %s (사용 가능: %s)",
                args.case, [c.id for c in EVAL_CASES],
            )
            return 1
    if args.only_eval:
        cases = [c for c in cases if c.category != "fallback"]
    if args.suite:
        cases = [c for c in cases if c.suite == args.suite]

    if not cases:
        logger.error("실행할 케이스 없음")
        return 1

    logger.info("=== W4 평가 시작 — %d 케이스 ===", len(cases))
    for c in cases:
        logger.info("  - [%s] %s [%s] %s",
                    c.suite, c.id, c.category, _truncate(c.question, 50))

    results: list[CaseEvalResult] = []
    started_total = time.perf_counter()

    for idx, case in enumerate(cases):
        logger.info(
            "\n=== [%d/%d] (%s) %s — %s ===",
            idx + 1, len(cases), case.suite, case.id,
            _truncate(case.question, 60),
        )
        try:
            if case.suite == "t2c":
                t2c = text2cypher(case.question)
                cer = _evaluate_t2c_case(case, t2c)
            elif case.suite == "local":
                lr = local_retrieve(case.question)
                cer = _evaluate_local_case(case, lr)
            elif case.suite == "router":
                rr = route_and_answer(case.question)
                cer = _evaluate_router_case(case, rr)
            else:
                raise ValueError(f"unknown suite: {case.suite}")
        except Exception as exc:
            logger.error("[%s] 예외: %s", case.id, exc)
            cer = CaseEvalResult(
                case_id=case.id,
                suite=case.suite,
                category=case.category,
                question=case.question,
                answer="",
                elapsed_seconds=0.0,
                error=f"{type(exc).__name__}: {exc}",
                verdict="FAIL",
                note=case.note,
            )
        results.append(cer)

        if not args.no_detail:
            if cer.suite == "t2c":
                _print_t2c_case_detail(cer)
            elif cer.suite == "local":
                _print_local_case_detail(cer)
            elif cer.suite == "router":
                _print_router_case_detail(cer)

    elapsed_total = time.perf_counter() - started_total
    logger.info("\n=== 평가 완료 — %d 케이스, %.1fs ===", len(results), elapsed_total)

    _print_summary_table(results)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with args.json.open("w", encoding="utf-8") as f:
            json.dump(
                [asdict(r) for r in results],
                f, ensure_ascii=False, indent=2,
            )
        logger.info("결과 JSON 박제: %s", args.json)

    fail_n = sum(1 for r in results if r.verdict == "FAIL")
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
