"""W3 batch — 평가 셋 8문서 일괄 적재.

`eval/dataset/documents/` 의 모든 파일을 순회하며 풀 파이프라인:
  parse_document (Layer A 구조화) → extract (Kimi) → link_entities (bge-m3)
  → build_layer_a → build_layer_b → link_chunks_to_entities (MENTIONS)

문서별 통계 (청크 / Entity / Relation / 소요시간 / 실패 여부) 수집 후
마지막에 표로 출력. weekly-log 박제 + 5/23 발표 자료 § 운영 데이터 시드.

사용:
    uv run python -m scripts.run_w3_batch
    uv run python -m scripts.run_w3_batch --limit 2  # 첫 2문서만 (sanity)
    uv run python -m scripts.run_w3_batch --pattern "*.pdf"  # PDF 만

전제조건:
    .env 에 KIMI_API_KEY / NEO4J_URI / NEO4J_PASSWORD / OPIK_*
    eval/dataset/documents/ 에 평가 셋 8문서 (gitignore — 로컬만)
    bge-m3 최초 1회 다운로드 완료 상태

#17 시행착오 / 운영 데이터:
- 본 스크립트 출력 표를 docs/weekly-log/2026-05-16-batch-ingest.md 에 박제
- Opik UI 에서 trace 페이지 캡처 → 발표 § How 슬라이드 시드

관련 이슈: #17 (본 작업), #13 #14 #15 (1청크 검증 끝), #24 (Opik on).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from agent.llm_client import configure_llm
from ingestion.adapter import parse_document
from ingestion.models import ChunkType, Document
from kg.builder import build_layer_a, build_layer_b, link_chunks_to_entities
from kg.extractor import extract
from kg.linking import link_entities
from kg.neo4j_client import Neo4jClient
from kg.ontology import ExtractionResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("w3-batch")

DOCS_DIR = Path("eval/dataset/documents")


@dataclass
class DocStat:
    """문서별 처리 통계 — 마지막에 표로 출력."""

    filename:           str
    source_format:      str
    doc_type:           str
    success:            bool             = False
    error:              str | None       = None

    sections:           int              = 0
    chunks_text:        int              = 0
    chunks_table:       int              = 0
    entities_raw:       int              = 0
    entities_grouped:   int              = 0
    relations:          int              = 0
    mentions:           int              = 0

    sec_parse:          float            = 0.0
    sec_extract:        float            = 0.0
    sec_linking:        float            = 0.0
    sec_neo4j:          float            = 0.0
    sec_total:          float            = 0.0


def _doc_to_extract_chunks(doc: Document) -> list[dict]:
    """Layer A Document → extract() 가 받는 chunk dict 리스트.

    옵션 3 (#17): chunk_id 키를 함께 박아 보내 entity local_id 에 global
    prefix 가 자동 부여되도록.
    """
    out: list[dict] = []
    for section in doc.sections:
        for chunk in section.chunks:
            # Table 은 별도 Layer A 노드. extractor 는 text 청크만 받는 게 단순.
            if chunk.chunk_type != ChunkType.TEXT:
                continue
            text = (chunk.text or "").strip()
            if not text:
                continue
            out.append({
                "doc_id":   doc.id,
                "chunk_id": chunk.id,           # ← #17 옵션 3 핵심 키
                "section":  section.original_section,
                "text":     text,
            })
    return out


async def _process_one(
    path: Path,
    client: Neo4jClient,
    *,
    create_indexes: bool,
) -> DocStat:
    """1 문서 풀 파이프라인. 실패해도 예외 안 던지고 stat 에 박제."""
    started_total = time.perf_counter()

    stat = DocStat(
        filename=path.name,
        source_format=path.suffix.lstrip(".").lower(),
        doc_type="(unknown)",
    )

    try:
        # 1. Parse — Layer A 구조화
        t0 = time.perf_counter()
        document = parse_document(path)
        stat.sec_parse = time.perf_counter() - t0
        stat.doc_type  = document.doc_type.value
        stat.sections  = len(document.sections)
        for sec in document.sections:
            stat.chunks_text  += len(sec.chunks)
            stat.chunks_table += len(sec.tables)

        logger.info(
            "[%s] Parse OK sections=%d chunks(text)=%d tables=%d (%.2fs)",
            path.name, stat.sections, stat.chunks_text, stat.chunks_table, stat.sec_parse,
        )

        # 2. Extract — Kimi
        chunks = _doc_to_extract_chunks(document)
        if not chunks:
            logger.warning("[%s] text 청크 없음 — extract skip", path.name)
            ext_result = ExtractionResult()
        else:
            t0 = time.perf_counter()
            ext_result = await extract(chunks)
            stat.sec_extract = time.perf_counter() - t0
        stat.entities_raw = len(ext_result.entities)
        stat.relations    = len(ext_result.relations)

        # 3. Linking — bge-m3 NED
        if ext_result.entities:
            t0 = time.perf_counter()
            link_result = link_entities(ext_result.entities)
            stat.sec_linking = time.perf_counter() - t0
            stat.entities_grouped = link_result.grouped_count
        else:
            from kg.linking import LinkingResult
            link_result = LinkingResult(groups=[], raw_count=0, grouped_count=0)

        # 4. Neo4j 적재 — Layer A + Layer B + MENTIONS
        t0 = time.perf_counter()
        build_layer_a(document, client=client, create_indexes=create_indexes)
        build_layer_b(link_result, ext_result.relations, client=client, create_indexes=False)
        mentions_result = link_chunks_to_entities(link_result, client=client)
        stat.sec_neo4j = time.perf_counter() - t0
        stat.mentions = mentions_result.mentions_merged

        stat.success = True

    except Exception as exc:
        stat.error = f"{type(exc).__name__}: {exc}"
        logger.error("[%s] 실패: %s", path.name, stat.error)
        logger.debug(traceback.format_exc())

    stat.sec_total = time.perf_counter() - started_total
    return stat


def _print_table(stats: list[DocStat]) -> None:
    """결과 표를 stdout 에 출력. weekly-log 에 그대로 복사 가능한 markdown."""
    print()
    print("## 8문서 일괄 적재 결과")
    print()
    print("| 파일 | 포맷 | 타입 | sec | chunks(T/B) | ent(raw→grp) | rel | mentions | parse | extract | link | neo4j | total | ok |")
    print("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for s in stats:
        ok = "✅" if s.success else "❌"
        rel_str = str(s.relations) if s.success else (s.error or "")[:30]
        print(
            f"| {s.filename} | {s.source_format} | {s.doc_type} | "
            f"{s.sections} | {s.chunks_text}/{s.chunks_table} | "
            f"{s.entities_raw}→{s.entities_grouped} | "
            f"{s.relations} | {s.mentions} | "
            f"{s.sec_parse:.1f} | {s.sec_extract:.1f} | "
            f"{s.sec_linking:.1f} | {s.sec_neo4j:.1f} | "
            f"{s.sec_total:.1f} | {ok} |"
        )
    print()

    ok_count = sum(1 for s in stats if s.success)
    print(f"총 {len(stats)}문서 · 성공 {ok_count} · 실패 {len(stats) - ok_count}")
    print(f"전체 소요: {sum(s.sec_total for s in stats):.1f}s")
    print(f"총 청크 (text): {sum(s.chunks_text for s in stats)}")
    print(f"총 entity raw: {sum(s.entities_raw for s in stats)}")
    print(f"총 entity grouped: {sum(s.entities_grouped for s in stats)}")
    print(f"총 relation: {sum(s.relations for s in stats)}")
    print(f"총 MENTIONS: {sum(s.mentions for s in stats)}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=None,
        help="처음 N 문서만 처리 (sanity 용). 기본: 전부.",
    )
    parser.add_argument(
        "--pattern", type=str, default="*",
        help="파일명 glob 패턴 (예: '*.pdf'). 기본: 전체.",
    )
    parser.add_argument(
        "--docs-dir", type=Path, default=DOCS_DIR,
        help="문서 디렉토리. 기본: eval/dataset/documents/",
    )
    # 추출 LLM 토글 (#56 P1 재인제스트) — run_qa_eval.py 와 동일 패턴.
    # 미지정 시 KIMI_* 기본. configure_llm() 이 전역 _active_config 를 세팅하므로
    # 이후 모든 LLMClient()(extractor 포함)가 이 모델을 사용.
    parser.add_argument("--llm-model", type=str, default=None,
                        help="추출 모델 ID (예: openai/gpt-5.2). 미지정 시 KIMI_*")
    parser.add_argument("--llm-base-url", type=str, default=None,
                        help="OpenAI 호환 endpoint (예: https://openrouter.ai/api/v1)")
    parser.add_argument("--llm-api-key-env", type=str, default="KIMI_API_KEY",
                        help="API 키 환경변수명 (예: OPENROUTER_API_KEY)")
    args = parser.parse_args()

    if args.llm_model or args.llm_base_url or args.llm_api_key_env != "KIMI_API_KEY":
        configure_llm(
            model=args.llm_model,
            base_url=args.llm_base_url,
            api_key_env=args.llm_api_key_env,
        )
        logger.info("추출 LLM 설정: model=%s base_url=%s", args.llm_model, args.llm_base_url)

    if not args.docs_dir.exists():
        logger.error("문서 디렉토리 없음: %s", args.docs_dir)
        return 1

    files = sorted(args.docs_dir.glob(args.pattern))
    files = [p for p in files if p.is_file()]
    if args.limit:
        files = files[: args.limit]

    if not files:
        logger.error("처리할 파일 없음 (dir=%s pattern=%s)", args.docs_dir, args.pattern)
        return 1

    logger.info("=== 8문서 일괄 적재 시작 — %d 파일 ===", len(files))
    for p in files:
        logger.info("  - %s", p.name)

    stats: list[DocStat] = []

    with Neo4jClient() as client:
        client.verify_connectivity()

        for idx, path in enumerate(files):
            logger.info("\n=== [%d/%d] %s ===", idx + 1, len(files), path.name)
            # 첫 문서만 인덱스 생성 시도 (멱등이라 매번 호출해도 OK 지만 절약)
            stat = await _process_one(
                path, client=client, create_indexes=(idx == 0),
            )
            stats.append(stat)

    _print_table(stats)
    return 0 if all(s.success for s in stats) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
