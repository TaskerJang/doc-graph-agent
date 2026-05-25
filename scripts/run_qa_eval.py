"""VectorRAG QA + GraphRAG QA 정량 평가 진입점 (#127).

doc-summary-agent 의 eval/run_eval.py 와 동일한 패턴으로:
- ROUGE-1/2/L + 수치 정확도 + Faithfulness Judge + Numerical Faithfulness Judge
- 4 측정 LLM 되이잘 (--llm-* 인자)
- Claude Haiku 4.5 judge (--judge-* 인자)

하지만 *답변 생성 경로* 는 doc-graph 의 retrieval.route_and_answer() —
Text2Cypher / Local Retriever / Community stub 가 자동 라우팅.

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ROOT             = Path(__file__).parent.parent
DATASET_DIR      = ROOT / "eval" / "dataset"
VECTORRAG_PATH   = DATASET_DIR / "vectorrag_qa.json"
GRAPHRAG_PATH    = DATASET_DIR / "graphrag_qa.json"
RESULT_DIR       = ROOT / "eval" / "results"
RESULT_DIR.mkdir(parents=True, exist_ok=True)


def _load_qa(qa_set: str) -> list[dict]:
    qa_pairs: list[dict] = []
    if qa_set in ("vectorrag", "both"):
        if VECTORRAG_PATH.exists():
            v = json.loads(VECTORRAG_PATH.read_text(encoding="utf-8"))
            for item in v:
                item.setdefault("qa_set", "vectorrag")
            qa_pairs.extend(v)
            logger.info("VectorRAG QA 로드: %d", len(v))
        else:
            logger.warning("VectorRAG QA 파일 없음: %s", VECTORRAG_PATH)
    if qa_set in ("graphrag", "both"):
        if GRAPHRAG_PATH.exists():
            g = json.loads(GRAPHRAG_PATH.read_text(encoding="utf-8"))
            for item in g:
                item.setdefault("qa_set", "graphrag")
            qa_pairs.extend(g)
            logger.info("GraphRAG QA 로드: %d", len(g))
        else:
            logger.warning("GraphRAG QA 파일 없음: %s", GRAPHRAG_PATH)
    return qa_pairs


def evaluate_one(qa: dict) -> dict:
    """단일 QA 에 대해 retrieval.route_and_answer() 호출 후 메트릭 계산."""
    question  = qa["question"]
    reference = qa.get("answer", "")

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

    rouge   = compute_rouge(prediction, reference)
    num_acc = compute_numerical_accuracy(prediction, reference)

    out = {
        "id":              qa["id"],
        "qa_set":          qa.get("qa_set", ""),
        "doc":              qa.get("doc", ""),
        "type":             qa.get("type", ""),
        "question":         question,
        "reference":        reference,
        "prediction":       prediction,
        "actual_route":     actual_route,
        "retrieval_error":  retrieval_error,
        "elapsed_seconds":  round(elapsed, 2),
        "rouge1":           rouge["rouge1"],
        "rouge2":           rouge["rouge2"],
        "rougeL":           rouge["rougeL"],
        "num_accuracy":     num_acc["accuracy"],
        "num_matched":      num_acc["matched"],
        "num_missed":       num_acc["missed"],
    }

    judge = judge_faithfulness(reference, prediction)
    out.update({
        "faithfulness":         judge.get("faithfulness", "Error"),
        "faithfulness_reason":  judge.get("faithfulness_reason", ""),
        "completeness":         judge.get("completeness", None),
        "conciseness":          judge.get("conciseness", None),
    })
    num_judge = judge_numerical_faithfulness(reference, prediction)
    out["numerical_faithfulness"]        = num_judge.get("numerical_faithfulness", "Error")
    out["numerical_faithfulness_reason"] = num_judge.get("reason", "")

    return out


def run_all(qa_pairs: list[dict], limit: int | None = None) -> list[dict]:
    if limit is not None:
        qa_pairs = qa_pairs[:limit]
    results = []
    for i, qa in enumerate(qa_pairs):
        logger.info("[%d/%d] (%s) %s", i + 1, len(qa_pairs),
                    qa.get("qa_set", ""), qa.get("id", "?"))
        r = evaluate_one(qa)
        results.append(r)
        logger.info(
            "  → route=%s ROUGE-L=%.3f Faithfulness=%s elapsed=%.1fs",
            r["actual_route"], r["rougeL"], r["faithfulness"], r["elapsed_seconds"],
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

    print("\n" + "=" * 70)
    print(f"📊 QA 평가 결과 요약  (총 {len(results)}개 QA)")
    print("=" * 70)

    for qa_set in ("vectorrag", "graphrag"):
        subset = [r for r in results if r.get("qa_set") == qa_set]
        if not subset:
            continue
        f, t = _faithful_rate(subset)
        print()
        print(f"## {qa_set.upper()} QA  (n={len(subset)})")
        print(f"  ROUGE-L:          {_avg(subset, 'rougeL'):.4f}")
        print(f"  수치 정확도:        {_avg(subset, 'num_accuracy'):.4f}")
        print(f"  Faithfulness:     {f}/{t} ({(f / t * 100) if t else 0:.1f}%)")
        print(f"  Completeness:     {_avg(subset, 'completeness'):.2f} / 5")
        print(f"  Conciseness:      {_avg(subset, 'conciseness'):.2f} / 5")
        routes: dict[str, int] = {}
        for r in subset:
            ar = r.get("actual_route") or "-"
            routes[ar] = routes.get(ar, 0) + 1
        route_str = ", ".join(f"{k}={v}" for k, v in sorted(routes.items()))
        print(f"  Routing 분포:    {route_str}")

    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description="VectorRAG + GraphRAG QA 정량 평가")
    parser.add_argument("--qa-set", choices=["vectorrag", "graphrag", "both"],
                        default="both", help="평가할 QA 셋. 기본 both.")
    parser.add_argument("--limit", type=int, default=None,
                        help="셜플링 앞에서 몇 개만. dry-run 용.")
    parser.add_argument("--tag", type=str, default="", help="결과 파일 태그")

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

    logger.info("=== QA 평가 시작 — %d QA ===", len(qa_pairs))
    started = time.perf_counter()
    results = run_all(qa_pairs, limit=args.limit)
    elapsed = time.perf_counter() - started
    logger.info("=== QA 평가 완료 — %d QA, %.1fs ===", len(results), elapsed)

    save_results(results, tag=args.tag)
    print_summary(results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
