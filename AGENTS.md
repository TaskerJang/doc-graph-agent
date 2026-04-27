# AGENTS.md

코딩 에이전트(Codex, Cursor 등)가 이 레포에서 작업할 때 참고할 컨텍스트.
Claude Code용 동일 내용은 `CLAUDE.md`에 둔다.

## 프로젝트 한 줄

인턴 시절 만든 VectorRAG 기반 `doc-summary-agent`를 SEOCHO Layer A/B/C 구조의 GraphRAG로 재구성한 멘토링 프로젝트.

## 우선순위

1. **시행착오의 흔적을 남긴다.** 코드 주석에 "왜 이렇게 했는지" 기록한다. 이슈 번호를 commit/주석에 박는다.
2. **재활용 vs 신규를 명확히 구분한다.** 기존 레포에서 포팅한 코드는 출처 주석을 단다. 신규 설계는 ADR로 기록한다.
3. **Layer 책임을 섞지 않는다.** Layer A/B/C는 검색 전략이 다르다. 한 함수에 두 Layer 로직이 섞이면 분리한다.
4. **평가 셋은 건드리지 않는다.** `eval/dataset/qa_pairs.json` (40개)은 Before/After 비교의 기준선이다. 추가는 가능하되 기존 항목은 수정 금지.

## 디렉토리 책임

| 디렉토리 | 책임 | 출처 |
|---|---|---|
| `ingestion/` | 문서 파싱 + 전처리 + 청킹 | 기존 doc-summary-agent의 `doc_parser/` + `chunker/` 포팅 |
| `kg/` | Entity 추출 + Linking + Neo4j 적재 | 신규 |
| `retrieval/` | Layer A/B/C 각 검색기 | 신규 |
| `agent/` | Routing Agent + Debate Pool | 신규 |
| `observability/` | Opik 트레이싱 + Span 정의 | 신규 |
| `eval/` | 평가 파이프라인 | 기존 `eval/` 그대로 재사용 |
| `ui/` | Chainlit UI | 기존 `ui/` 포팅 |

## Layer 분리 규칙

| Layer | 노드 | 검색 도구 | 적합한 질문 |
|---|---|---|---|
| A: Document Structure | Document, Section, Chunk, Table | Text-to-Cypher | "X 보고서의 Y 섹션" |
| B: Entity Interaction | Entity (Company, Metric, Risk, Outlook) | Local Retriever + Subgraph | "A와 B의 관계" |
| C: Community/Topic | Community, Topic | Community Summary | "전체 흐름" |

Layer 간 cross-cutting 로직은 `agent/router.py`에만 둔다. retrieval 모듈은 자기 Layer만 안다.

## 코드 스타일

- Python 3.11+, type hints 필수.
- async I/O는 `asyncio.to_thread`로 블로킹 호출 격리 (기존 레포의 reranker cold start 패턴 참고).
- LLM 호출은 `tenacity` retry로 감싼다.
- Neo4j 쿼리는 read-only 안전 장치 + bounded result (LIMIT) 필수.

## 커밋 메시지

```
태그(스코프): #이슈번호 한 줄 설명

[필요 시 본문 — 왜 이렇게 했는지]
```

태그: `feat`, `fix`, `perf`, `refactor`, `revert`, `docs`, `test`, `chore`.

## 작업 시 체크리스트

- [ ] 관련 이슈 번호를 commit message·주석에 박았는가?
- [ ] 기존 레포에서 포팅한 코드라면 출처 주석을 달았는가?
- [ ] 새 설계 결정이라면 `docs/adr/`에 짧게라도 기록했는가?
- [ ] Layer 경계를 침범하지 않았는가?
- [ ] 평가 셋 동일성을 유지했는가?
- [ ] Opik `@track` 데코레이터를 적절한 함수에 붙였는가? (W5 이후)

## 참고 자료

- 기존 레포: https://github.com/TaskerJang/doc-summary-agent
- 멘토링 커리큘럼: 사용자 노트 참조
- 책: *Knowledge Graphs and LLMs in Action* (Negro et al., Manning 2025)
- 책: *Graph Data Science with Python and Neo4j* (Eastridge 2024)
