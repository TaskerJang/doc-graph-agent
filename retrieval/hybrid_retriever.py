"""Hybrid Retriever — BM25 ⊕ PPR Reciprocal Rank Fusion (Plan B).

graph 라우트에서 **두 검색기를 동시에** 돌려 청크 랭킹을 RRF 로 융합한다:
- BM25 (어휘 fulltext): 정확 수치·고유명사·종목 리스트에 강함 (factual).
- PPR (그래프 활성화): 관계·인과·멀티홉 트렌드에 강함.

4편 부검 근거:
- bm25 가 종목리스트/factual(graph_013·015·018·024·039·040)을 구제하고,
  ppr 가 trend/causal 을 이김 — 두 검색기가 **상보적**. 라우팅은 한쪽만 고르므로
  나머지의 강점을 버린다. RRF 로 합치면 best-of-both.
- Cormack et al. (2009): RRF score(d) = Σ_L 1/(k + rank_L(d)), k=60. 점수 스케일이
  다른 랭킹(BM25 Lucene score vs PPR 확률)을 **순위만으로** 안전하게 결합 — 정규화
  불필요, 이상치에 강건.

흐름:
  자연어 질문
     ├─ _bm25_chunks (Neo4j fulltext, LLM 0)            → bm25 ranked chunks
     └─ ppr_retrieve(...).retrieved_chunks               → ppr ranked chunks
        ↓ _rrf_fuse (chunk_id 기준 RRF, top-k)
     fused chunks
        ↓ _generate_answer (LLM 1회, bm25_answer 프롬프트 재사용)
     자연어 답변

설계 결정:
- **청크 레벨 융합** (답변 레벨 아님): 두 검색기의 청크를 합친 뒤 답변은 1회만 생성 →
  근거 일관성 + 비용 절감.
- ppr 는 공개 `ppr_retrieve` 의 retrieved_chunks 사용 (private 의존 회피 → ppr v1/v2
  내부 변경에 robust). 단점은 ppr 답변 1콜 낭비 — 실험 단계에서 허용. (hybrid 가
  이기면 ppr 에 chunks-only 진입점 추가로 최적화.)
- 답변 프롬프트는 중립적 청크 기반인 bm25_answer_v1.md 재사용 (새 프롬프트 불필요).

안전장치:
1. read-only — 하위 검색기 모두 조회 전용.
2. graceful — 한쪽 0건이어도 다른 쪽으로 융합; 둘 다 0건이면 note 와 함께 안내.
3. 결과 크기 제한 — PER_RETRIEVER_K / TOP_K_CHUNKS.

#24 Opik:
- 공개 진입점 `hybrid_retrieve` 에 `@track`. 하위 ppr_retrieve 의 @track 은 nested span.

Reference:
- retrieval/bm25_retriever.py — `_bm25_chunks` (chunks-only) 재사용.
- retrieval/ppr_retriever.py — `ppr_retrieve` retrieved_chunks 재사용.
- Cormack, Clarke, Buettcher (2009) "Reciprocal Rank Fusion outperforms Condorcet
  and individual Rank Learning Methods" (SIGIR) — RRF, k=60.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.llm_client import LLMClient
from kg.neo4j_client import Neo4jClient
from observability.tracing import track

# bm25 의 chunks-only 함수 + 중립 답변 프롬프트 재사용
from retrieval.bm25_retriever import (
    ANSWER_PROMPT_PATH as BM25_ANSWER_PROMPT_PATH,
    _bm25_chunks,
    _load_prompt,
)
from retrieval.ppr_retriever import ppr_retrieve

logger = logging.getLogger(__name__)


# ── 상수 ─────────────────────────────────────────────────────
TEMPERATURE_ANSWER = 0.3
MAX_TOKENS_ANSWER = 700

RRF_K = 60               # Cormack 2009 기본값
PER_RETRIEVER_K = 8      # 각 검색기에서 가져올 후보 청크 수
TOP_K_CHUNKS = 8         # 융합 후 답변에 넘길 청크 수


# ── 결과 객체 ────────────────────────────────────────────────
@dataclass
class HybridRetrieverResult:
    """Hybrid(RRF) retriever 한 회차의 전체 trace."""

    question: str
    bm25_chunks: list[dict[str, Any]] = field(default_factory=list)
    ppr_chunks: list[dict[str, Any]] = field(default_factory=list)
    fused_chunks: list[dict[str, Any]] = field(default_factory=list)
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)  # = fused (호환)
    n_chunks: int = 0
    retrieved_context: str = ""   # E1: faithfulness judge 대조용 (fused 청크 text join)
    answer: str = ""
    elapsed_seconds: float = 0.0
    error: str | None = None


# ── RRF 융합 ─────────────────────────────────────────────────
def _rrf_fuse(
    ranked_lists: list[list[dict[str, Any]]],
    k: int = RRF_K,
    top_k: int = TOP_K_CHUNKS,
) -> list[dict[str, Any]]:
    """여러 ranked 청크 리스트를 Reciprocal Rank Fusion 으로 결합.

    score(c) = Σ_L 1/(k + rank_L(c)) (rank 1-indexed). 점수 스케일 무관, 순위만 사용.
    """
    scores: dict[str, float] = {}
    meta: dict[str, dict[str, Any]] = {}
    for ranked in ranked_lists:
        for rank, ch in enumerate(ranked, start=1):
            cid = ch.get("chunk_id")
            if not cid:
                continue
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            meta.setdefault(cid, ch)

    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    out: list[dict[str, Any]] = []
    for cid, s in fused:
        m = dict(meta[cid])
        m["rrf_score"] = round(s, 6)
        out.append(m)
    return out


# ── 답변 생성 ────────────────────────────────────────────────
@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _call_llm_text(llm: LLMClient, system_prompt: str, user_prompt: str) -> str:
    return llm.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=TEMPERATURE_ANSWER,
        max_tokens=MAX_TOKENS_ANSWER,
    )


def _generate_answer(
    llm: LLMClient,
    question: str,
    chunks: list[dict[str, Any]],
    answer_system_prompt: str,
    note: str = "",
) -> str:
    """질문 + 융합 청크 → 자연어 답변. 0건/실패 모두 LLM 에 넘겨 안내."""
    user_payload = {
        "question": question,
        "retrieved_chunks": chunks,
        "note": note,
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)
    try:
        answer = _call_llm_text(llm, answer_system_prompt, user_prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Hybrid 답변 생성 LLM 호출 실패: %s", exc)
        if not chunks:
            return note or "검색된 자료에서 답을 찾지 못했습니다."
        return f"{len(chunks)}개 청크를 검색했으나 자연어 변환에 실패했습니다."
    return answer.strip()


# ── 공개 인터페이스 ──────────────────────────────────────────
@track
def hybrid_retrieve(
    question: str,
    llm: LLMClient | None = None,
    neo4j: Neo4jClient | None = None,
) -> HybridRetrieverResult:
    """자연어 질문 → BM25 + PPR 청크 → RRF 융합 → 자연어 답변.

    Args:
        question: 사용자 자연어 질문.
        llm: 테스트용 mock 주입 가능. 기본 LLMClient().
        neo4j: 테스트용 mock 주입 가능. 기본 Neo4jClient().

    Returns:
        HybridRetrieverResult — 전체 trace 포함. answer 는 항상 채워짐.
    """
    started = time.perf_counter()
    if not question or not question.strip():
        return HybridRetrieverResult(
            question=question,
            answer="질문이 비어 있습니다. 무엇이 궁금한지 입력해 주세요.",
            elapsed_seconds=time.perf_counter() - started,
        )

    llm = llm or LLMClient()
    own_neo4j = neo4j is None
    neo4j = neo4j or Neo4jClient()

    answer_system_prompt = _load_prompt(BM25_ANSWER_PROMPT_PATH)
    logger.info("HybridRetriever 시작 — question=%r", question)

    try:
        # 1) 두 검색기에서 ranked 청크 (bm25 는 LLM 0, ppr 는 공개 진입점)
        bm25_chunks, bm25_err = _bm25_chunks(neo4j, question, top_k=PER_RETRIEVER_K)
        ppr_res = ppr_retrieve(question, llm=llm, neo4j=neo4j)
        ppr_chunks = ppr_res.retrieved_chunks or []

        # 2) RRF 융합
        fused = _rrf_fuse([bm25_chunks, ppr_chunks])
        context = "\n\n".join((c.get("text") or "") for c in fused).strip()

        # 3) 답변 생성 (융합 청크로 1회)
        note = "" if fused else (bm25_err or ppr_res.error or "양쪽 검색 모두 0건입니다.")
        answer = _generate_answer(
            llm, question, fused, answer_system_prompt, note=note
        )

        elapsed = time.perf_counter() - started
        logger.info(
            "HybridRetriever 완료 — bm25=%d ppr=%d fused=%d elapsed=%.2fs",
            len(bm25_chunks), len(ppr_chunks), len(fused), elapsed,
        )
        return HybridRetrieverResult(
            question=question,
            bm25_chunks=bm25_chunks,
            ppr_chunks=ppr_chunks,
            fused_chunks=fused,
            retrieved_chunks=fused,
            n_chunks=len(fused),
            retrieved_context=context,
            answer=answer,
            elapsed_seconds=elapsed,
            error=note or None,
        )
    finally:
        if own_neo4j:
            neo4j.close()
