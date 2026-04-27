# Before / After: VectorRAG → GraphRAG 매핑

기존 [`doc-summary-agent`](https://github.com/TaskerJang/doc-summary-agent)에서 드러난 한계를 SEOCHO Layer A/B/C로 어떻게 푸는지 정리한다. 발표 서사 "Why GraphRAG"의 근거 자료.

---

## 매핑 표

| # | Before: VectorRAG에서의 문제 | 코드 증거 | After: GraphRAG 해결 가설 | 검증 Layer |
|---|---|---|---|---|
| 1 | **Completeness 1.25/5** — 흩어진 정보 통합 실패 | `eval/leaderboard.md` | Community Summary가 토픽 단위로 정보 통합 | Layer C |
| 2 | **메타데이터를 정규식+키워드로 짜냄** (`doc_year`, `section_type`, `metrics`) | `chunker/chunker.py` `_extract_*` 함수들 (#75) | Entity 노드/관계로 자연 표현 — 추출 정확도와 표현력 동시 향상 | Layer B |
| 3 | **chunk_size 튜닝 지옥** (300→700, overlap 50→200) | `chunker/chunker.py` 주석 "LLM 호출 폭발" | 청크 경계 의존도를 그래프 traversal로 완화 | Layer A/B |
| 4 | **Section ↔ Chunk 출처 매칭 실패** | `summarizer/qa.py` `_make_sources` 주석 (#111) "순서 대응이 보장되지 않는다" | Section -[:CONTAINS]-> Chunk 명시적 관계 | Layer A |
| 5 | **하이브리드 검색 복잡도** (BM25 + Dense + RRF + Reranker) | `summarizer/qa.py` 380줄, reranker cold start 2분 (#107) | 질문 유형별 Layer 라우팅 — 단일 검색 전략 강제 안 함 | Cross |
| 6 | **수치 정확도 71%** — 표 청크가 텍스트와 동급 취급 | `chunker/chunker.py` `_is_table_block` (#59) | 수치는 Entity로 추출 — 출처·단위·연도 동시 추적 | Layer B |
| 7 | **OCR 노이즈 사후 정규식 제거** | `summarizer/qa.py` `_OCR_NOISE_RE` | 인제스트 단계에서 Entity가 안 되는 노이즈는 자연 탈락 | Layer A 진입 전 |
| 8 | **추천 질문이 overall 요약에만 의존** | `summarizer/qa.py` `generate_follow_ups` | Entity-Entity 관계 기반 질문 생성 | Layer B |

---

## 발표 시 강조 포인트

- **#1 Completeness 1.25/5**가 가장 강력한 "왜 GraphRAG" 근거다. 수치가 압도적으로 낮아서 개선 여지가 명확하다.
- **#2 메타데이터 정규식**이 가장 직관적인 사례다. 코드 자체가 "이걸 그래프로 했어야 했다"고 외치고 있다.
- **#5 하이브리드 검색 복잡도**는 "단일 전략 강제의 한계"를 보여주기 좋다. Layer 라우팅의 동기 자체.

---

## TODO

- [ ] W1 종료 시점에 동일 평가 셋으로 Before 베이스라인 **재측정** (기존 결과는 BM25 단독 시점 — 하이브리드 도입 후 미측정)
- [ ] W6 종료 시점에 GraphRAG After 측정
- [ ] 두 결과를 leaderboard에 병기 — 발표 자료 자동 생성
