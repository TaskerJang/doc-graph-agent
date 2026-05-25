# QA Datasets — doc-graph-agent

## VectorRAG QA (40 고)

`vectorrag_qa.json` — doc-summary-agent 의 40 QA 그대로 복사.
- factual / numerical / summary / negative 유형
- 한와/DS/미래에셋/농협/금감원 5 문서
- 텍스트 chunk 검색으로 답변 가능한 질의 (RAG 강점)

## GraphRAG QA (40 계획)

`graphrag_qa.json` — 그래프 구조 활용 질의 (Graph 강점).

### 작성 패턴
1. **1-hop 관계** (7) — entity A 와 함께 언급된 B
2. **2-hop 다중** (7) — entity A → chunk → entity B → chunk → entity C
3. **교집합** (7) — 두 entity 의 공통 속성
4. **집계/통계** (7) — 전체 그래프 최대/최소/평균
5. **필터 + 집계** (6) — doc_type / doc_year 필터 후 집계
6. **메타데이터** (6) — 문서 개수, 섹션 구조, 첥크 분포

### 작성 순서
1. `scripts/explore_graph.py` 실행 → 그래프 메타 추출
2. 결과를 보면서 40 QA 작성
3. 각 QA 의 정답은 Cypher 쿼리로 곀증 가능해야 함
