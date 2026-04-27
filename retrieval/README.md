# retrieval/

**책임**: Layer A/B/C 각각의 검색기. **Layer 간 cross-cutting 로직 금지** — 라우팅은 `agent/router.py`에서.

**출처**: 신규.

## 모듈 (예정)

- `layer_a_text2cypher.py` — 자연어 → Cypher 변환 (read-only, bounded result)
- `layer_b_local.py` — Entity 시드 → subgraph 확장
- `layer_c_community.py` — Community Summary 기반 응답

## 안전 장치

- Layer A는 read-only Cypher만 허용 (CREATE/DELETE/MERGE/SET 거부)
- 모든 결과는 `LIMIT` 강제 (default 1000행)
- Syntax 검증 후 실행

## 참고

- 책: *Knowledge Graphs and LLMs in Action* Ch 14~15 (Asking KG Questions, QA Agent)
- 책: *Graph Data Processing with Cypher* Ch 1~3, 5
