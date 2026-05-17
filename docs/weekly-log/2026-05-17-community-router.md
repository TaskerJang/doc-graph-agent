# W4 — Community Summary stub + Routing Agent (#20 + #21)

**2026-05-17 (Sun) — 코드 트랙 두 번째 세션**

W4 마무리. Layer C (Community Summary) stub + Layer A/B/C 통합 라우팅 에이전트 박제.
PR #49 (#19 Local Retriever) 머지 직후 진행 — 시나리오 A 의 5/18 일정을 하루 당겨 5/17 안에 W4 전체 완료.

## 작업 컨텍스트

- **선행 머지**: PR #49 (L4 PASS + Discovery 3 + L5 글로벌 fallback) 5/17 00:26 UTC 머지 (`438c1422`)
- **남은 W4 이슈**: #20 (Community Summary stub), #21 (Routing Agent)
- **목표**: 발표 슬라이드 13 (Local 데모) ✅ + 14 (Routing 명분) 의 R3 community stub 시연 강화
- **데이터 환경**: Aura `9b57188f` (8 문서 / 610 노드 / 2,451 관계 / 1,189 MENTIONS, 5/16 적재)

## 레퍼런스 조사

| 출처 | 통찰 | 적용 |
|------|------|------|
| Microsoft GraphRAG (2024-04) | Community Summary 는 **indexing time 에 사전 생성**. Global Search 는 map-reduce 로 community report 위에서 동작 | community detection / report 생성이 우리 환경에 없음 → 정직한 stub 만 (#20) |
| Microsoft GraphRAG 4 mode | Global / Local / DRIFT / Basic 으로 분류. DRIFT 는 Local + Global 합성 | 본 작전 외. 향후 W5+ DRIFT 검토 가능 |
| Sotaaz blog (2026-01) | `hybrid_search()` 의 if/elif/else 결정적 분기 — `is_global_question(q)` → global, `contains_entity(q)` → local | 우리 `_classify_by_keywords` 의 직접 모델 (#21) |
| LangChain `MultiRetrievalQAChain` | LLM router 표준 패턴. 그러나 *"same query may route to different sources"* (TDS 2025) 비일관성 | LLM 라우팅을 1단계로 안 두는 결정의 근거 |
| LangChain `EmbeddingRouterChain` | Semantic router — 각 route 의 예시 prompt 를 embedding 해두고 query 최근접 라우트 선택 | W5+ 확장 후보 (이번 PR 스코프 외, 사유: embedding API 추가) |
| Neo4j `ToolsRetriever` | `convert_to_tool(name, description)` 후 LLM 자동 선택 — agent-style routing | LLM fallback 의 system prompt 모델 (각 retriever 의 description 명시) (#21) |
| NeoConverse blog (2025-08) | *"Intelligent fallback mechanism — Defaults gracefully to Text2Cypher when no suitable agentic tool is identified"* | 우리 `DEFAULT_ROUTE = "t2c"` 의 산업 선례 (#21) |
| Memgraph Atomic GraphRAG (2026-03) | Analytical / Local / Global 의 3-way 분류 — 우리와 동일 | Routing 셋 R1~R3 의 매핑 그대로 (t2c=Analytical, local=Local, community=Global) |

## 설계 결정 (5/17 박제)

### #20 Community Summary — 순수 stub 으로 결정

- **거짓말 안 하기**: Microsoft GraphRAG 의 Global Search 는 community detection + community report 가 indexing time 에 생성되어 있어야 동작. 우리는 둘 다 없음. LLM 만으로 글로벌 답변 흉내내면 "그래프 기반" 이라는 표현이 거짓이 됨.
- **stub 응답 구성**: 글로벌 질의 분류 확인 + Layer C 미구현 명시 + 5/24+ ETA + 대안 안내 (Layer A/B 활용 권장).
- **LLM/Neo4j 호출 0회** → 즉시 응답 + Opik `@track` trace 만 남김.
- **인터페이스 박제**: `CommunitySummaryResult(answer, is_stub=True)` — 미래 진짜 Layer C 와 시그니처 호환 유지 의도.

### #21 Routing Agent — 키워드 분기 + LLM fallback

- **결정적 키워드 우선** — LangChain LLM router 의 일관성 문제 (TDS 2025) 회피. 디버깅 / 평가 / 발표 시연 모두 명확.
- **LLM fallback 은 필요한 만큼만** — 키워드 매칭 0개 시에만 호출. 단순 factual 질문 (Q1~Q6) 은 LLM 호출 없이 t2c 로 즉시 라우팅 → 비용 0, 지연 0.
- **graceful default = t2c** — LLM 실패 / unknown route → t2c 로 fallback (NeoConverse 패턴).

**키워드 매핑**:
- `LOCAL_KEYWORDS`: 관계, 관련, 연관, 영향, 함께, 이웃, 어떻게, co-mention, 관계는, 관련된, 연관된
- `COMMUNITY_KEYWORDS`: 트렌드, 전체, 흐름, 주요 트렌드, 주제, 패턴, 주요 흐름, 전반, 글로벌, community, communities, topic, topics, themes, 전체적, 통합, 사전체
- 그 외 → t2c

**Tie-break**: 두 셋 동시 매칭 시 더 많은 쪽. 동률이면 community 우선 (전체 질의는 보통 community 의도).

## 변경 사항

**신규**
- `retrieval/community_summary.py` — Layer C stub 진입점 (`@track`, 138 lines)
- `retrieval/prompts/community_summary_v1.md` — W5+ 실제 구현 시 채울 placeholder
- `retrieval/router.py` — Routing Agent (`decide_route`, `route_and_answer`, 424 lines)
- `retrieval/prompts/router_v1.md` — LLM fallback system prompt + 5 few-shot

**수정**
- `retrieval/__init__.py` — 신규 export 8개 추가
- `scripts/run_w4_eval.py` — `expected_route` 필드 + R1~R3 케이스 + `--suite router` + routing 결과 표

## 평가 셋 R1~R3 — 기존 Q*/L* 의도 재활용

| ID | 출처 | 질문 | 기대 라우트 | 검증 포인트 |
|----|------|------|-------------|-------------|
| **R1** | Q2 동일 | "미래에셋증권 4분기 보고서의 Table 은 몇 개?" | `t2c` | 키워드 매칭 0개 → **LLM fallback 트리거 검증** + t2c 답변 "6" |
| **R2** | L1 변형 | "두산밥캣과 함께 언급된 리스크는 어떻게 관련되어 있나?" | `local` | "관련/함께/어떻게" **3중 매칭** → local 즉시 분기 |
| **R3** | L5 동일 | "전체 8문서의 주요 트렌드와 흐름은?" | `community` | "트렌드/전체/흐름/주요 트렌드" **4중 매칭** → community **stub 응답** 검증 |

R2 는 5/17 정성 검증 시 두산밥캣 entity 매칭 0개로 graceful fallback 가는 케이스 (PR #49 박제 내용 그대로) — 라우팅은 PASS, retriever 내부 fallback 동작 검증 겸함.

## 실행 방법

```bash
git pull
# Routing 전용 평가
uv run python -m scripts.run_w4_eval --suite router --json eval/w4_router_2026-05-17.json

# 전체 (Q* + F* + L* + R*)
uv run python -m scripts.run_w4_eval

# 개별 case
uv run python -m scripts.run_w4_eval --case R2
```

## DoD

**#20 Community Summary stub**
- [x] `community_summary(question)` 진입점 — Layer C 미구현 안내 응답
- [x] `CommunitySummaryResult` 시그니처 박제 (is_stub=True)
- [x] `@track` Opik trace
- [x] LLM/Neo4j 호출 0회 (정직한 stub)
- [x] R3 케이스로 평가 통합

**#21 Routing Agent**
- [x] 키워드 분기 1단계 (`_classify_by_keywords`)
- [x] LLM fallback 2단계 (`_classify_by_llm`) — JSON 응답 강제, tenacity 2 attempts
- [x] graceful default = t2c
- [x] 통합 진입점 `route_and_answer` (`@track`)
- [x] R1~R3 평가 셋 + `--suite router` 옵션
- [x] `decide_route` / `route_and_answer` export

## 정성 검증 결과 (5/17 10:02 KST 로컬 실행)

**3/3 PASS · 라우팅 정확도 100% · 전체 소요 12.8s · Routing 평균 4.3s**

| ID | category | verdict | expected | actual | match | llm? | matched_keywords | elapsed |
|----|----------|---------|:--------:|:------:|:-----:|:----:|------------------|--------:|
| R1 | routing-factual | **PASS** | t2c | t2c | ✅ | ✅ | — | 7.2s |
| R2 | routing-relation | **PASS** | local | local | ✅ | — | 관련, 함께, 어떻게 | 5.6s |
| R3 | routing-global | **PASS** | community | community | ✅ | — | 트렌드, 전체, 흐름, 주요 트렌드 | 0.0s |

### R1 — LLM fallback 트리거 검증 ✅

- 키워드 매칭 0개 → LLM fallback 진입 (의도)
- Kimi reasoning: *"특정 문서 내의 Table 개수를 묻는 명시적 사실 질문. Text2Cypher가 aggregation 쿼리를 통해 처리할 수 있다."* → t2c 라우팅
- t2c 결과: `MATCH (d:Document {filename: '미래에셋증권_4분기_실적보고서.pdf'})-[:HAS_SECTION]->(:Section)-[:CONTAINS_TABLE]->(t:Table) RETURN count(t) AS table_count` → 6
- 답변: *"미래에셋증권 4분기 실적보고서에는 총 6개의 표(Table) 가 적재되어 있습니다."* (Q2 답과 일치)

### R2 — 키워드 3중 매칭 + graceful fallback ✅

- 키워드 3개 매칭 (관련 / 함께 / 어떻게) → local 즉시 분기 (LLM 호출 없음, 결정적)
- 두산밥캣 entity 매칭 0개 → graceful fallback 응답 (L1 PASS 의 동일 fallback 메시지 재현)
- 라우팅 정확도 PASS + retriever 내부 fallback 동작 검증 겸함

### R3 — Community stub 즉시 응답 ✅

- 키워드 4개 매칭 (트렌드 / 전체 / 흐름 / 주요 트렌드) → community 즉시 분기
- LLM/Neo4j 호출 0회 → **elapsed 0.0s** (의도대로)
- 답변: 글로벌 질의 분류 확인 + Layer C 미구현 명시 + Layer A/B 대안 안내
- Answer hint hits 5/5 (stub 메시지의 핵심 키워드 모두 포함)

### Opik trace

- 프로젝트: `hyunsang-doc-graph-agent`
- 모든 R* 케이스의 라우팅 decision + 하위 retriever 호출이 nested span 으로 박제됨
- R1 의 LLM fallback 호출 + t2c 의 schema 추출 / Cypher 생성 / 실행 3-step 도 분리 확인

## 발표 슬라이드 연결

- **슬라이드 14 (Routing 명분)** ← R3 community stub 시연으로 강화. PR #49 까지는 L5 PASS 만 있었음 (local_retriever 내부의 "Layer C 적합 안내" fallback). 본 PR 머지 후엔 **명시적 routing decision trace** (matched_keywords, llm_used 필드) + Layer C stub 응답으로 시연 가능.
- R1 의 LLM fallback reasoning ("aggregation 쿼리를 통해 처리할 수 있다") 도 발표 데모로 활용 가능 — "키워드 없는 모호한 질문도 LLM 이 reasoning 후 라우팅".
- R2 의 키워드 3중 매칭 trace 도 흥미로움 — Opik nested span 으로 "라우팅 → entity 매칭 0개 → graceful fallback" 의 3단계 시각화 가능.

## 후속

- **Issue #50** (Entity 추출 한계 — Company 라벨에 회사명 자체 부재) — 5/24+ W5 영역, 발표 전 해결 불요. 본 PR 과 독립.
- **W5+ Layer C 실제 구현**: community detection (Leiden / Louvain) → community report 생성 → 진짜 Global Search 구현. 본 PR 의 stub 시그니처를 그대로 활용 가능.
- **Semantic Router 확장**: LangChain `EmbeddingRouterChain` 패턴으로 키워드 어휘 한계 보완. embedding API 도입 후 검토.
