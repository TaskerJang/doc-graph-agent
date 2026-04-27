# Document Structure Ontology (Layer A)

> Status: **DRAFT** · 본격 작성 예정 (W2)

## 목적

출처 추적과 원문 인용을 위한 문서 구조 그래프. "X 보고서의 Y 섹션 Z 페이지" 같은 질문이 명시적으로 풀려야 한다.

## 노드 (예정)

- `Document` — 업로드된 PDF/DOCX/HWP 단위
- `Section` — Markdown heading 기준 (`#`, `##`, `###`)
- `Chunk` — Section 내부 분할 단위
- `Table` — 표 청크 (별도 처리)

## 관계 (예정)

- `Document -[:HAS_SECTION]-> Section`
- `Section -[:HAS_SUBSECTION]-> Section`
- `Section -[:CONTAINS]-> Chunk`
- `Section -[:CONTAINS]-> Table`
- `Chunk -[:NEXT]-> Chunk` (순서 보존)

## 기존 레포와의 차이

기존 `chunker/chunker.py`의 `Chunk` TypedDict는 `section`을 단순 문자열로 가졌다. 이로 인해 `summarizer/qa.py` `_make_sources`에서 "Section ↔ Chunk 순서 대응 보장 안 됨" (#111) 문제가 발생했다.

명시적 관계로 표현하면 이 문제가 구조적으로 사라진다.
