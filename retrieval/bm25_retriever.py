"""BM25 Retriever — 어휘 fulltext 검색 (Plan A, Hybrid 1단계).

자연어 질문 → Neo4j fulltext 인덱스(`chunk_fulltext`, Lucene/BM25 스코어) →
top-k 청크 → 자연어 답변.

기존 Layer A(text2cypher) / Layer B(local_retrieve) 와 달리 **그래프 구조를
전혀 타지 않는다**. entity 식별·MENTIONS traversal 없이 Chunk.text 를 어휘
매칭으로 직접 검색 → entity→MENTIONS 병목을 우회.

왜 만들었나 (근거):
- chunk-rerank 네거티브 결과(#70)가 가리킨 처방: 병목은 청크 *랭킹*이 아니라
  후보 풀(graph-anchored, MENTIONS-only). 어휘 검색은 그 풀을 우회한다.
- BEIR (Thakur et al. 2021, arXiv 2104.08663): BM25 는 OOD 에서 dense 를 자주
  능가하는 robust baseline. 정확 수치·고유명사(목표주가/종목코드/매출액)에서 강함.
- 본 프로젝트 80 QA 에서 doc-summary(BM25) 가 factual/numerical 을 압승
  (AC 4.0 / Faithful 92% vs doc-graph 2.0 / 15~17%) — 같은 처방을 doc-graph 에 이식.

한국어 주의:
- fulltext 인덱스는 **cjk analyzer** 로 생성해야 함 (standard 는 공백 분리만 →
  "두산밥캣의" ≠ "두산밥캣" 매칭 실패). 인덱스 DDL:
    CREATE FULLTEXT INDEX chunk_fulltext IF NOT EXISTS
    FOR (c:Chunk) ON EACH [c.text]
    OPTIONS {indexConfig: {`fulltext.analyzer`: 'cjk'}}

안전장치:
1. read-only — queryNodes 는 조회 전용, 사용자 입력은 parameterized + Lucene escape.
2. 결과 크기 제한 — TOP_K_CHUNKS / CHUNK_TEXT_TRUNCATE 로 토큰 폭발 방지.
3. graceful fallback — 인덱스 부재 / 0건 / LLM 실패 모두 자연어 안내.

#24 Opik:
- 공개 진입점 `bm25_retrieve` 에 `@track`.

Reference:
- text2cypher.py / local_retriever.py — LLM 호출 / 프롬프트 로드 / @track 패턴 그대로.
- Cormack et al. 2009 (RRF) — 추후 graph 검색과 융합 시 사용 (Plan B).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
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

logger = logging.getLogger(__name__)


# ── 상수 (text2cypher / local 과 일치) ───────────────────────
TEMPERATURE_ANSWER = 0.3
MAX_TOKENS_ANSWER = 700

FULLTEXT_INDEX = "chunk_fulltext"   # cjk analyzer 로 생성된 Chunk.text fulltext 인덱스
TOP_K_CHUNKS = 8                    # BM25 상위 N 청크 (어휘 검색은 graph 보다 넉넉히)
CHUNK_TEXT_TRUNCATE = 600           # 청크 1개당 char 상한 (LLM 컨텍스트용)

PROMPTS_DIR = Path(__file__).parent / "prompts"
ANSWER_PROMPT_PATH = PROMPTS_DIR / "bm25_answer_v1.md"

# Lucene 쿼리 특수문자 — escape 대상 (사용자 입력이 쿼리 연산자로 해석되는 것 방지)
_LUCENE_SPECIAL_RE = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')


# ── 결과 객체 ────────────────────────────────────────────────
@dataclass
class BM25RetrieverResult:
    """BM25 retriever 한 회차의 전체 trace.

    Opik / 디버깅용 모든 중간 산물 보존.
    """

    question: str
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    n_chunks: int = 0
    answer: str = ""
    elapsed_seconds: float = 0.0
    error: str | None = None


# ── 프롬프트 로드 ────────────────────────────────────────────
def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── 쿼리 sanitize ────────────────────────────────────────────
def _sanitize_query(question: str) -> str:
    """사용자 질문을 Lucene fulltext 쿼리로 안전하게 변환.

    특수문자를 escape 해 Lucene 연산자로 오해석되는 것을 막는다. cjk analyzer 가
    토큰화(bigram)하므로 별도 토큰 분해는 하지 않고, 양끝 공백만 정리.
    """
    if not question:
        return ""
    escaped = _LUCENE_SPECIAL_RE.sub(r"\\\1", question)
    return re.sub(r"\s+", " ", escaped).strip()


# ── BM25 fulltext 검색 ───────────────────────────────────────
# db.index.fulltext.queryNodes — Lucene 스코어(BM25) 내림차순. 인덱스 부재 시
# Cypher 예외 → 호출부에서 graceful 처리.
_BM25_CYPHER = """
CALL db.index.fulltext.queryNodes($index_name, $query) YIELD node, score
RETURN node.id AS chunk_id,
       node.text AS text,
       properties(node).page AS page,
       score
ORDER BY score DESC
LIMIT $top_k
"""


def _bm25_chunks(
    neo4j: Neo4jClient, query: str, top_k: int = TOP_K_CHUNKS
) -> tuple[list[dict[str, Any]], str | None]:
    """fulltext 인덱스에서 top-k 청크 검색.

    Returns:
        (chunks, error). 인덱스 부재 / 빈 쿼리 / 0건 모두 ([], reason) 로 graceful.
        chunks 각 원소: {chunk_id, text(truncated), page, score}
    """
    q = _sanitize_query(query)
    if not q:
        return [], "빈 질문입니다."
    try:
        rows = neo4j.read(
            _BM25_CYPHER, index_name=FULLTEXT_INDEX, query=q, top_k=top_k
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("BM25 fulltext 검색 실패 (인덱스 미생성 가능): %s", exc)
        return [], (
            f"fulltext 인덱스 '{FULLTEXT_INDEX}' 검색 실패 — "
            f"인덱스가 생성되지 않았을 수 있습니다: {exc}"
        )

    chunks: list[dict[str, Any]] = []
    for r in rows:
        cid = r.get("chunk_id")
        text = r.get("text")
        if not cid or not text:
            continue
        chunks.append(
            {
                "chunk_id": cid,
                "text": text[:CHUNK_TEXT_TRUNCATE],
                "page": r.get("page"),
                "score": round(float(r.get("score") or 0.0), 3),
            }
        )

    if not chunks:
        return [], "fulltext 검색 결과 0건."
    return chunks, None


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
    """질문 + BM25 청크 → 자연어 답변. 0건 / 실패 모두 LLM 에 그대로 넘겨 안내."""
    import json

    user_payload = {
        "question": question,
        "retrieved_chunks": chunks,
        "note": note,
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)

    try:
        answer = _call_llm_text(llm, answer_system_prompt, user_prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("BM25 답변 생성 LLM 호출 실패: %s", exc)
        if not chunks:
            return note or "검색된 자료에서 답을 찾지 못했습니다."
        return f"{len(chunks)}개 청크를 검색했으나 자연어 변환에 실패했습니다."

    return answer.strip()


# ── 공개 인터페이스 ──────────────────────────────────────────
@track
def bm25_retrieve(
    question: str,
    llm: LLMClient | None = None,
    neo4j: Neo4jClient | None = None,
    top_k: int = TOP_K_CHUNKS,
) -> BM25RetrieverResult:
    """자연어 질문 → BM25 fulltext 검색 → top-k 청크 → 자연어 답변.

    Args:
        question: 사용자 자연어 질문.
        llm: 테스트용 mock 주입 가능. 기본 LLMClient().
        neo4j: 테스트용 mock 주입 가능. 기본 Neo4jClient().
        top_k: 검색할 청크 수.

    Returns:
        BM25RetrieverResult — 전체 trace 포함. answer 는 항상 채워짐.
    """
    started = time.perf_counter()
    if not question or not question.strip():
        return BM25RetrieverResult(
            question=question,
            answer="질문이 비어 있습니다. 무엇이 궁금한지 입력해 주세요.",
            elapsed_seconds=time.perf_counter() - started,
        )

    llm = llm or LLMClient()
    own_neo4j = neo4j is None
    neo4j = neo4j or Neo4jClient()

    answer_system_prompt = _load_prompt(ANSWER_PROMPT_PATH)
    logger.info("BM25Retriever 시작 — question=%r", question)

    try:
        chunks, error = _bm25_chunks(neo4j, question, top_k=top_k)
        answer = _generate_answer(
            llm, question, chunks, answer_system_prompt, note=error or "",
        )
        elapsed = time.perf_counter() - started
        logger.info(
            "BM25Retriever 완료 — chunks=%d elapsed=%.2fs error=%r",
            len(chunks), elapsed, error,
        )
        return BM25RetrieverResult(
            question=question,
            retrieved_chunks=chunks,
            n_chunks=len(chunks),
            answer=answer,
            elapsed_seconds=elapsed,
            error=error,
        )
    finally:
        if own_neo4j:
            neo4j.close()
