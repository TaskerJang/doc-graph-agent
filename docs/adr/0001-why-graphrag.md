# ADR-0001: VectorRAG 대신 GraphRAG를 채택한 이유

## Status

Accepted (2026-04-27)

## Context

인턴 시절 구축한 [`doc-summary-agent`](https://github.com/TaskerJang/doc-summary-agent)는 BM25 + bge-m3 + RRF + bge-reranker-v2-m3 기반의 정교한 하이브리드 VectorRAG 시스템이다. 그럼에도 다음 한계가 측정되었다 (40 QA, `prompt_v2_bm25`, `chunk_size=500`, `overlap=50` 기준):

- ROUGE-L: 0.2929
- 수치 정확도: 0.7102
- Faithfulness: 31/40 (77.5%)
- **Completeness: 1.25 / 5**
- Conciseness: 3.90 / 5

특히 **Completeness 1.25/5**는 "흩어진 정보 통합" 유형의 질문에서 VectorRAG가 구조적으로 약하다는 신호다. 청크 단위 retrieval은 "전체적으로 어떤 흐름인가" 류의 질문을 청크 5개로 답하기 어렵다.

또한 코드 자체에서 다음 패턴이 반복된다:

- `chunker/chunker.py` `_SECTION_TYPE_MAP`, `_METRIC_KEYWORDS` — 메타데이터를 정규식·키워드로 짜내고 있다
- `summarizer/qa.py` `_make_sources` — Section ↔ Chunk 순서 대응이 보장되지 않는다 (#111)
- 청크 크기 튜닝의 끊임없는 시행착오 (300 → 700, overlap 50 → 200)

이는 "문서 구조와 도메인 의미를 평면 청크에 강제로 우겨넣은 결과"로 해석된다.

## Decision

SEOCHO 플랫폼의 3-Layer 구조를 채택한다.

- **Layer A (Document Structure)**: 출처 추적 — Text-to-Cypher
- **Layer B (Entity Interaction)**: 의미 관계 — Local Retriever + Subgraph
- **Layer C (Community/Topic)**: 글로벌 통합 — Community Summary

VectorRAG의 retrieval 코어는 폐기하고, 파싱·UI·평가 셋은 재활용한다.

## Consequences

### 좋은 점
- Completeness 약점에 직접 대응 (Layer C)
- 메타데이터를 명시적 그래프 구조로 표현
- 질문 유형별 검색 전략 분기 가능 (Routing Agent)
- 출처 추적이 명시적 관계로 풀림 — `_make_sources` 매칭 문제 해소

### 나쁜 점
- KG 구축 파이프라인 신규 개발 부담 (W3 집중)
- Entity 추출·Linking 정확도가 전체 품질의 새 병목
- Neo4j/DozerDB 운영 학습 곡선
- 6주 내 동일 평가 셋에서 Before를 넘지 못할 리스크 — 그러나 "왜 안 됐나"의 분석도 발표 자료가 됨

### 트레이드오프 인정
동일 평가 셋(40 QA)에서 GraphRAG가 모든 지표에서 VectorRAG를 이길 보장은 없다. 특히 Faithfulness나 Conciseness는 retrieval 전략 변경의 직접적 수혜 대상이 아니다. 발표는 "GraphRAG가 모든 면에서 우월하다"가 아니라 "어떤 질문 유형에서 어떻게 다른가"를 보여주는 것을 목표로 한다.
