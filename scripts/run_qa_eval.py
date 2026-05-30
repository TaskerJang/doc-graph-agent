"""VectorRAG QA + GraphRAG QA 정량 평가 진입점 (#127).

doc-summary-agent 의 eval/run_eval.py 와 동일한 패턴 + Tier 2 메트릭 4개 추가:

## 메트릭 (Tier 1 + Tier 2)

### Tier 1 — 전통 + FineSurE (#127 초기 박힘)
- ROUGE-1/2/L (전통)
- 수치 정확도 (커스텀 금융 특화)
- Faithfulness / Completeness / Conciseness (FineSurE ACL 2024)
- Numerical Faithfulness (수치 충실도)

### Tier 2 — RAGAS + GraphRAG-Bench (#127 확장)
- Answer Correctness (RAGAS + GraphRAG-Bench Accuracy) — 의미적 일치 1-5점
- Semantic Similarity (RAGAS) — bge-m3 cosine
- Entity Coverage (RAGAS Context Entities Recall 변형) — 정답 entity 등장률
- Routing Accuracy (GraphRAG-Bench AR Metric 변형) — expected vs actual route

## 답변 생성 경로

doc-graph 의 retrieval.route_and_answer() — Text2Cypher / Local / Community
자동 라우팅.

## 데이터셋 (단일 소스)

단일 소스 `eval/dataset/qa_pairs.json` 하나만 읽고, 각 항목의 `qa_set`
필드("vectorrag"/"graphrag")로 분리한다. 분리 파일(vectorrag_qa.json /
graphrag_qa.json)을 수동으로 쪼개던 방식은 합본과 분리본이 어긋나
(예: 글자 손상) 측정이 오염되는 문제가 있어 폐지했다.
결과는 qa_set 별로 분리 집계된다(print_summary 2개 섹션 + 결과 JSON의 qa_set).

## 사용

    # 전체 80 QA (VectorRAG 40 + GraphRAG 40) 측정
    uv run python scripts/run_qa_eval.py \\
      --llm-model "deepseek/deepseek-v3.2" \\
      --llm-base-url "https://openrouter.ai/api/v1" \\
      --llm-api-key-env "OPENROUTER_API_KEY" \\
      --judge-model "anthropic/claude-haiku-4.5" \\
      --judge-base-url "https://openrouter.ai/api/v1" \\
      --judge-api-key-env "OPENROUTER_API_KEY" \\
      --qa-set both \\
      --tag deepseek_both

    # VectorRAG QA 만
    uv run python scripts/run_qa_eval.py --qa-set vectorrag --tag <태그>

    # GraphRAG QA 만
    uv run python scripts/run_qa_eval.py --qa-set graphrag --tag <태그>

    # 소규모 dry-run (처음 3 QA 만)
    uv run python scripts/run_qa_eval.py --qa-set vectorrag --limit 3 --tag dryrun

    # semantic similarity 메트릭 끄기 (CPU 환경에서 빠른 dry-run)
    uv run python scripts/run_qa_eval.py --no-semantic --qa-set graphrag --limit 5
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.llm_client import configure_llm
from retrieval.router import route_and_answer

from eval.metrics.rouge_score import compute_rouge
from eval.metrics.numerical_accuracy import compute_numerical_accuracy
from eval.metrics.faithfulness_judge import (
    judge_faithfulness,
    judge_numerical_faithfulness,
    configure_judge_llm,
)
from eval.metrics.answer_correctness import judge_answer_correctness
from eval.metrics.entity_coverage import compute_entity_coverage
from eval.metrics.routing_accuracy import compute_routing_accuracy

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ROOT             = Path(__file__).parent.parent
DATASET_DIR      = ROOT / "eval" / "dataset"
QA_PATH          = DATASET_DIR / "qa_pairs.json"   # 단일 소스 (vectorrag + graphrag 합본)
RESULT_DIR       = ROOT / "eval" / "results"
RESULT_DIR.mkdir(parents=True, exist_ok=True)


def _infer_qa_set(item: dict) -> str:
    """qa_set 필드 누락 시 추론 — graphrag QA 만 pattern/expected_route 를 가진다."""
    if item.get("pattern") or item.get("expected_route"):
        return "graphrag"
    return "vectorrag"


def _load_qa(qa_set: str) -> list[dict]:
    """단일 데이터셋(qa_pairs.json)을 읽어 qa_set 으로 필터링.

    수동으로 분리한 vectorrag_qa.json / graphrag_qa.json 을 읽던 방식은
    합본과 분리본이 어긋나(글자 손상 등) 측정이 오염되는 문제가 있었다.
    이제 단일 소스만 읽고, 각 항목의 qa_set 필드로 분리한다. 결과 집계는
    기존대로 qa_set 별로 분리되어 나온다(print_summary / 결과 JSON).

    Args:
        qa_set: "vectorrag" | "graphrag" | "both"
    """
    if not QA_PATH.exists():
        logger.error("QA 데이터셋 파일 없음: %s", QA_PATH)
        return []

    all_qa = json.loads(QA_PATH.read_text(encoding="utf-8"))

    # qa_set 필드 보정 — 누락 시 추론
    for item in all_qa:
        if not item.get("qa_set"):
            item["qa_set"] = _infer_qa_set(item)

    if qa_set == "both":
        selected = all_qa
    else:
        selected = [q for q in all_qa if q.get("qa_set") == qa_set]

    n_vec = sum(1 for q in selected if q.get("qa_set") == "vectorrag")
    n_gr  = sum(1 for q in selected if q.get("qa_set") == "graphrag")
    logger.info("QA 로드: %s (qa_set=%s) — vectorrag=%d, graphrag=%d, total=%d",
                QA_PATH.name, qa_set, n_vec, n_gr, len(selected))
    if not selected:
        logger.warning("선택된 QA 0개 — qa_set=%s 항목이 %s 에 있는지 확인", qa_set, QA_PATH.name)
    return selected


def evaluate_one(qa: dict, use_semantic: bool = True) -> dict:
    """단일 QA 에 대해 retrieval.route_and_answer() 호출 후 메트릭 계산.

    Args:
        qa: QA 항목 — id, question, answer, qa_set, [expected_route], [key_entities]
        use_semantic: True 면 bge-m3 semantic_similarity 계산. CPU 환경에서 느리면 False.
    """
    question  = qa["question"]
    reference = qa.get("answer", "")
    qa_set    = qa.get("qa_set", "")
    expected_route = qa.get("expected_route")  # GraphRAG QA 만 박힘
    key_entities   = qa.get("key_entities", [])  # GraphRAG QA 만 박힘

    # ── 답변 생성 ──────────────────────────────────────────
    started = time.perf_counter()
    try:
        result = route_and_answer(question)
        prediction = result.answer or "[답변 불가]"
        actual_route = result.decision.route
        retrieval_error = None
    except Exception as e:
        logger.error("[%s] retrieval 예외: %s", qa.get("id", "?"), e)
        prediction = "[retrieval error]"
        actual_route = None
        retrieval_error = f"{type(e).__name__}: {e}"
    elapsed = time.perf_counter() - started

    # ── Tier 1 메트릭 ──────────────────────────────────────
    rouge   = compute_rouge(prediction, reference)
    num_acc = compute_numerical_accuracy(prediction, reference)

    out = {
        "id":              qa["id"],
        "qa_set":          qa_set,
        "doc":             qa.get("doc", ""),
        "type":            qa.get("type", ""),
        "pattern":         qa.get("pattern", ""),  # GraphRAG QA pattern
        "question":        question,
        "reference":       reference,
        "prediction":      prediction,
        "actual_route":    actual_route,
        "retrieval_error": retrieval_error,
        "elapsed_seconds": round(elapsed, 2),
        # Tier 1 — 전통
        "rouge1":          rouge["rouge1"],
        "rouge2":          rouge["rouge2"],
        "rougeL":          rouge["rougeL"],
        "num_accuracy":    num_acc["accuracy"],
        "num_matched":     num_acc["matched"],
        "num_missed":      num_acc["missed"],
    }

    # Tier 1 — Faithfulness Judge (FineSurE)
    judge = judge_faithfulness(reference, prediction)
    out.update({
        "faithfulness":        judge.get("faithfulness", "Error"),
        "faithfulness_reason": judge.get("faithfulness_reason", ""),
        "completeness":        judge.get("completeness", None),
        "conciseness":         judge.get("conciseness", None),
    })
    num_judge = judge_numerical_faithfulness(reference, prediction)
    out["numerical_faithfulness"]        = num_judge.get("numerical_faithfulness", "Error")
    out["numerical_faithfulness_reason"] = num_judge.get("reason", "")

    # ── Tier 2 메트릭 ──────────────────────────────────────

    # Answer Correctness (RAGAS + GraphRAG-Bench) — LLM Judge 1-5
    ac = judge_answer_correctness(question, reference, prediction)
    out["answer_correctness"]        = ac.get("answer_correctness", None)
    out["answer_correctness_reason"] = ac.get("reason", "")

    # Semantic Similarity (RAGAS) — bge-m3 cosine, optional
    if use_semantic:
        try:
            from eval.metrics.semantic_similarity import compute_semantic_similarity
            sim = compute_semantic_similarity(prediction, reference)
            out["semantic_similarity"] = sim.get("semantic_similarity", None)
        except Exception as e:
            logger.warning("semantic_similarity 스킵: %s", e)
            out["semantic_similarity"] = None
    else:
        out["semantic_similarity"] = None

    # Entity Coverage (RAGAS Context Entities Recall 변형)
    ec = compute_entity_coverage(prediction, reference, key_entities=key_entities)
    out["entity_coverage"]         = ec["entity_coverage"]
    out["entity_matched"]          = ec["matched"]
    out["entity_missed"]           = ec["missed"]
    out["entity_total"]            = ec["total"]

    # Routing Accuracy (GraphRAG-Bench AR Metric 변형) — GraphRAG QA 만 의미
    ra = compute_routing_accuracy(expected_route, actual_route)
    out["routing_correct"]  = ra["routing_correct"]
    out["expected_route"]   = ra["expected"]

    return out


def run_all(qa_pairs: list[dict], limit: int | None = None, use_semantic: bool = True) -> list[dict]:
    if limit is not None:
        qa_pairs = qa_pairs[:limit]
    results = []
    for i, qa in enumerate(qa_pairs):
        logger.info("[%d/%d] (%s) %s", i + 1, len(qa_pairs),
                    qa.get("qa_set", ""), qa.get("id", "?"))
        r = evaluate_one(qa, use_semantic=use_semantic)
        results.append(r)
        logger.info(
            "  → route=%s ROUGE-L=%.3f Faithful=%s Correctness=%s elapsed=%.1fs",
            r["actual_route"], r["rougeL"], r["faithfulness"],
            r.get("answer_correctness"), r["elapsed_seconds"],
        )
    return results


def save_results(results: list[dict], tag: str = "") -> Path:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"qa_eval_{tag}_{ts}.json" if tag else f"qa_eval_{ts}.json"
    path = RESULT_DIR / name
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("결과 저장: %s", path)
    return path


def print_summary(results: list[dict]) -> None:
    if not results:
        print("결과 없음")
        return

    def _avg(rs: list[dict], key: str) -> float:
        vals = [r[key] for r in rs if isinstance(r.get(key), (int, float))]
        return sum(vals) / len(vals) if vals else 0.0

    def _faithful_rate(rs: list[dict]) -> tuple[int, int]:
        f = sum(1 for r in rs if r.get("faithfulness") == "Faithful")
        return f, len(rs)

    def _routing_rate(rs: list[dict]) -> tuple[int, int]:
        considered = [r for r in rs if r.get("routing_correct") is not None]
        correct = sum(1 for r in considered if r.get("routing_correct"))
        return correct, len(considered)

    print("\n" + "=" * 78)
    print(f"📊 QA 평가 결과 요약  (총 {len(results)}개 QA)")
    print("=" * 78)

    for qa_set in ("vectorrag", "graphrag"):
        subset = [r for r in results if r.get("qa_set") == qa_set]
        if not subset:
            continue
        f, t = _faithful_rate(subset)
        rc_correct, rc_total = _routing_rate(subset)
        print()
        print(f"## {qa_set.upper()} QA  (n={len(subset)})")
        print(f"  ── Tier 1 (전통 + FineSurE) ──")
        print(f"  ROUGE-L:               {_avg(subset, 'rougeL'):.4f}")
        print(f"  수치 정확도:             {_avg(subset, 'num_accuracy'):.4f}")
        print(f"  Faithfulness:          {f}/{t} ({(f / t * 100) if t else 0:.1f}%)")
        print(f"  Completeness:          {_avg(subset, 'completeness'):.2f} / 5")
        print(f"  Conciseness:           {_avg(subset, 'conciseness'):.2f} / 5")
        print(f"  ── Tier 2 (RAGAS + GraphRAG-Bench) ──")
        print(f"  Answer Correctness:    {_avg(subset, 'answer_correctness'):.2f} / 5")
        print(f"  Semantic Similarity:   {_avg(subset, 'semantic_similarity'):.4f}")
        print(f"  Entity Coverage:       {_avg(subset, 'entity_coverage'):.4f}")
        if rc_total > 0:
            print(f"  Routing Accuracy:      {rc_correct}/{rc_total} ({(rc_correct / rc_total * 100):.1f}%)")
        print(f"  ── 진단 ──")
        routes: dict[str, int] = {}
        for r in subset:
            ar = r.get("actual_route") or "-"
            routes[ar] = routes.get(ar, 0) + 1
        route_str = ", ".join(f"{k}={v}" for k, v in sorted(routes.items()))
        print(f"  Routing 분포:         {route_str}")
        avg_elapsed = _avg(subset, "elapsed_seconds")
        print(f"  평균 응답:            {avg_elapsed:.1f}s")

    print("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser(description="VectorRAG + GraphRAG QA 정량 평가")
    parser.add_argument("--qa-set", choices=["vectorrag", "graphrag", "both"],
                        default="both", help="평가할 QA 셋. 기본 both.")
    parser.add_argument("--limit", type=int, default=None,
                        help="앞에서 몇 개만. dry-run 용.")
    parser.add_argument("--tag", type=str, default="", help="결과 파일 태그")
    parser.add_argument("--no-semantic", action="store_true",
                        help="Semantic Similarity 메트릭 끄기 (bge-m3 CPU 부담)")

    parser.add_argument("--llm-model", type=str, default=None)
    parser.add_argument("--llm-base-url", type=str, default=None)
    parser.add_argument("--llm-api-key-env", type=str, default="KIMI_API_KEY")

    parser.add_argument("--judge-model", type=str, default=None)
    parser.add_argument("--judge-base-url", type=str, default=None)
    parser.add_argument("--judge-api-key-env", type=str, default="OPENAI_API_KEY")

    args = parser.parse_args()

    if args.llm_model or args.llm_base_url or args.llm_api_key_env != "KIMI_API_KEY":
        configure_llm(
            model=args.llm_model,
            base_url=args.llm_base_url,
            api_key_env=args.llm_api_key_env,
        )
        logger.info("측정 LLM 설정: %s", args.llm_model)

    if args.judge_model or args.judge_base_url or args.judge_api_key_env != "OPENAI_API_KEY":
        configure_judge_llm(
            model=args.judge_model,
            base_url=args.judge_base_url,
            api_key_env=args.judge_api_key_env,
        )
        logger.info("Judge LLM 설정: %s", args.judge_model)

    qa_pairs = _load_qa(args.qa_set)
    if not qa_pairs:
        logger.error("QA 없음 — qa_set=%s", args.qa_set)
        return 1

    logger.info("=== QA 평가 시작 — %d QA (semantic=%s) ===",
                len(qa_pairs), not args.no_semantic)
    started = time.perf_counter()
    results = run_all(qa_pairs, limit=args.limit, use_semantic=not args.no_semantic)
    elapsed = time.perf_counter() - started
    logger.info("=== QA 평가 완료 — %d QA, %.1fs ===", len(results), elapsed)

    save_results(results, tag=args.tag)
    print_summary(results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
