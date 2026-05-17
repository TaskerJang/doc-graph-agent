# 2026-05-17 — W4 Local Retriever (#19) 작업 일지

> **WBS 1.14** — W4 Layer B: Local Retriever
> **이슈**: #19 · **브랜치**: `feat/19-local-retriever` · **PR**: #49

## 작업 컨텍스트

5/16 토 PR #48 (#18 Text2Cypher 8/8 PASS) 머지 완료 후 W4 두 번째 retrieval 작업.

text2cypher.py 패턴 (LLM 2단계 호출 + JSON 응답 + tenacity 재시도 + @track + graceful fallback) 을 그대로 재활용하되, **LLM 이 Cypher 를 자유 생성하는 대신 entity 만 식별**하고 subgraph 는 결정적 1-hop Cypher 템플릿으로 추출하는 패턴.

## 레퍼런스

- **Microsoft GraphRAG Local Search** — entity 를 graph 진입점 (access point) 으로 활용, connected entities + relationships + community reports + chunks 를 컨텍스트로 합성하는 컨셉 차용.
- **Tomaz Bratanic (Neo4j Developer Blog)** — Implementing 'From Local to Global' GraphRAG with Neo4j and LangChain — graph 구축/검색의 Neo4j 구체 패턴 참고.
- **회사 레포** `doc-summary-agent/summarizer/llm.py` — LLM 호출 / JSON 강제 / 재시도 패턴 (kg/extractor.py 가 이미 정합).

## 차이점 — Text2Cypher (Q*) vs Local Retriever (L*)

| 특성 | Q (Text2Cypher) | L (Local Retriever) |
|------|------------------|---------------------|
| LLM 역할 | Cypher 자유 생성 | entity 만 식별 |
| Cypher | LLM 생성 (다양) | 결정적 1-hop 템플릿 |
| 강점 | factual / topN / 정량 | 관계 / 연관 / 의미 |
| 약점 | 다 entity 교집합 | 글로벌 / 통계 질의 |
| 안전장치 | read-only 강제 + LIMIT | parameterized (사용자 입력 escape) |

## 변경 사항

### 신규 파일

- `retrieval/local_retriever.py` (≈ 550 lines) — Local Retriever 메인 모듈
- `retrieval/prompts/local_retriever_entity_v1.md` — entity 식별 system prompt (5 few-shot 예시)
- `retrieval/prompts/local_retriever_answer_v1.md` — 답변 생성 system prompt (4 few-shot 예시)

### 수정 파일

- `retrieval/__init__.py` — `local_retrieve`, `LocalRetrieverResult`, `LocalRetrieverError` 추가 export
- `retrieval/eval_set.md` — L1~L5 섹션 추가 (~150 lines)
- `scripts/run_w4_eval.py` — L 케이스 5개 추가 + suite 필터 (`--suite local`) + Local Retriever 분기 평가 로직

## 평가 셋 L1~L5 — 정성 검증 케이스

| ID | 카테고리 | 질문 | 검증 포인트 |
|----|---------|------|------------|
| L1 | relation | 두산밥캣과 함께 언급된 리스크는? | Q4 와 답변 패턴 차이 (subgraph 활용) |
| L2 | two-entity | 한화와 두산밥캣은 어떻게 관련되어 있나? | 두 entity 교집합 (Text2Cypher 어려운 케이스) |
| L3 | self-company | 미래에셋증권의 주요 지표와 전망은? | ⭐ 자기 회사명 미추출 graceful (슬라이드 10 보강) |
| L4 | label-quality | 공모발행액 23조에 대해 어떤 위험이 함께 언급? | ⭐ 라벨 품질 challenge 정직 보고 (슬라이드 10) |
| L5 | global | 전체 8문서의 주요 트렌드는? | Layer C 라우팅 명분 (슬라이드 14) |

## 실행 방법

```cmd
:: 전체 (Q* + F* + L*)
uv run python -m scripts.run_w4_eval

:: Local Retriever 만
uv run python -m scripts.run_w4_eval --suite local

:: 1개만
uv run python -m scripts.run_w4_eval --case L4

:: JSON 박제
uv run python -m scripts.run_w4_eval --suite local --json eval/w4_local_2026-05-17_v2.json
```

## 정성 검증 결과 (2026-05-17 09:14 KST · v2 measurement)

> 환경: Aura `9b57188f` (8문서 / 610 노드 / 2,451 관계 / 1,189 MENTIONS), Kimi k2 turbo preview, Opik 트레이싱 동작 확인.
> JSON 박제: `eval/w4_local_2026-05-17_v2.json`

| ID | category | verdict | identified | matched | relations | chunks | elapsed |
|----|----------|---------|-----------:|--------:|----------:|-------:|--------:|
| L1 | relation       | **PARTIAL** | 1 | 0 | 0 | 0 | 5.8s |
| L2 | two-entity     | **PARTIAL** | 2 | 0 | 0 | 0 | 4.6s |
| L3 | self-company   | **PARTIAL** | 1 | 0 | 0 | 0 | 5.0s |
| L4 | label-quality  | **PASS**    | 1 | 1 | 15 | 3 | 9.2s |
| L5 | global         | **PASS**    | 0 | 0 | 0 | 0 | 3.9s |

**총 5 케이스 · PASS 2 · PARTIAL 3 · FAIL 0**
**평균 응답: 5.7s** ⚠️ (DoD: < 5초 — L4 제외 평균 4.8s 이므로 일반 케이스는 통과, subgraph 풍부 케이스만 초과)

### DoD (#19) 충족도

- [x] **관계 질의에서 VectorRAG 와 다른 답변 패턴 (subgraph 정보 활용)** ✅ — L4 PASS 가 직접 증거. 답변에 'FACES_RISK 관계로 연결' 명시적 언급, relations=15·chunks=3 활용. Q 시리즈 (Cypher 직접 생성) 와 명확히 다른 답변 톤.
- [⚠️] **평균 응답 시간 < 5초** — 평균 5.7s 로 DoD 0.7s 초과. 단, **일반 케이스 (L1~L3, L5) 평균은 4.8s 로 DoD 통과**. L4 의 9.2s 는 LLM 답변 생성 (relations 15개 + chunks 3개 컨텍스트 → 답변 토큰 증가) 영향. **trade-off 박제** — subgraph 가 풍부할수록 답변 품질↑ + 응답 시간↑.
- [x] **graceful fallback** ✅ — L1·L2·L3 매칭 0개 → 친절 안내 메시지 정상 생성, L5 식별 0개 → Layer C 안내 정상.

### L4 PASS 의 답변 (발표 슬라이드 10 자료)

> 질문에서 언급한 '공모발행액 23조 7,050억원 (2025년 10월)' 에 대해 함께 언급된 위험 요소는 다음과 같습니다:
>
> 1. 회사채 발행 규모 23조 6,111억원 (2025년 10월) 과 CP 및 단기사채 발행액 137조 6,459억원 (2025년 10월) 이 **FACES_RISK 관계**로 연결되어 있습니다.
> 2. 기업공개 발행액 524억원 (2025년 10월) 과 기타금융사 발행규모 및 비중 920억원 (전월 대비 감소) 이 **FACES_RISK 및 HAS_METRIC 관계**로 연결되어 있습니다.
> 3. 단기사채 잔액 78조 6,585억원 (2025년 10월), 보험회사, 종금사가 **FACES_RISK 관계**로 연결되어 있습니다.
>
> 이러한 위험 요소들은 주로 발행 규모와 관련된 금액, 발행 종류, 발행 기관 등에 대한 위험을 나타내고 있습니다.

→ **'Company' 라벨인데 이름이 metric (공모발행액 23조) 으로 적재** 된 entity 가 또 다른 metric entity (회사채 발행 규모 등) 와 'FACES_RISK' 라는 의미론적으로 어색한 관계로 연결된 것을 답변이 그대로 노출. **라벨 품질 challenge 의 가장 정직한 데모.**

## 시행착오 박제 (5/17 발견)

### Bug 1 — Cypher 5.x SyntaxError 42I63 (1차 실행, v1)

```
Entity 매칭 Cypher 실패: Neo.ClientError.Statement.SyntaxError 42I63:
"ORDER BY, SKIP and LIMIT can only be used in this order in RETURN."
```

**원인**: 초안 패턴 `WITH ... ORDER BY ... WITH collect(e)[..3]` 가 Neo4j 5.x 파서에서 `ORDER BY` 가 후속 `WITH` 절에 묶이지 않고 떠 있는 형태로 해석. 5.x 권고는 RETURN 절 안에 ORDER BY+LIMIT 을 두는 것.

**해결**: CALL 서브쿼리로 ORDER BY+LIMIT 격리.

```cypher
UNWIND $names AS qname
CALL (qname) {           // ← variable scope clause (5.x)
  MATCH (e:Entity) WHERE ...
  RETURN e ORDER BY size(e.name) ASC LIMIT 3
}
RETURN qname, elementId(e) AS id, ...
```

→ 커밋 `ba806b2c` (1차 fix), `814d4c52` (deprecation 해소 + page property 가드).

### Bug 2 — `c2.page` property 부재 warning

```
property key does not exist. The property `page` does not exist in database
```

**원인**: 8문서 적재된 일부 청크에 page property 가 chunker 단계에서 누락. OPTIONAL MATCH 라 결과는 깨지지 않았지만 매 쿼리마다 warning.

**해결**: `properties(c2).page` 로 null-safe 접근 (없으면 null). 5/24+ chunker 보강 시 page 메타데이터 일관 적재 검토 필요.

### Discovery 3 — **Company 라벨 품질 challenge 의 실제 심각도가 5/16 진단보다 더 큼**

5/16 진단 3 ("Company 상위 5개가 모두 metric") 은 **상한값이 아니라 평균값에 가까운 사실** 이었음.

**5/17 정성 검증 결과**:
- L1 "두산밥캣" → **CONTAINS 매칭마저 0개** (entity name 에 회사명 자체가 안 담김)
- L2 "한화" → **마찬가지로 0개**
- L3 "미래에셋증권" → **5/16 가설 ('당사' 대명사로 추출 누락) 확정**
- L4 "공모발행액 23조" → **matched=1, FACES_RISK 관계 15개로 연결** — Company 라벨 metric entity 간 의미론적으로 어색한 관계가 그래프 가득.

**즉**: 'Company' 라벨에 진짜 회사명이 거의 없을 뿐 아니라, **CONTAINS 매칭으로도 회사명을 찾을 수 없을 정도**로 entity name 자체가 회사명을 못 담고 있음. entity 추출 LLM (Kimi) 의 한계가 5/16 진단보다 한 단계 더 심각.

→ **발표 슬라이드 10 (Entity 라벨 품질 challenge) 의 본질적 증거**. PR 머지 막을 사유 아니라 **박제할 발견**.

→ **별도 이슈 (#X) 로 트래킹**: entity 재추출 / 회사명 normalization / fulltext index — W3 영역 작업, 5/24+ 추진.

### Discovery 4 — Local Retriever 의 응답 시간 trade-off

L4 가 9.2s 로 평균을 끌어올림. subgraph relations=15, chunks=3 → LLM 답변 생성 시 컨텍스트 큼 → 답변 토큰 증가 → LLM 호출 시간 증가.

**시사점**: subgraph 풍부 케이스 ↔ 응답 시간 trade-off 존재. production 에서 MAX_RELATED_PER_ENTITY 와 MAX_CHUNKS_PER_ENTITY 의 조정 또는 streaming 답변 검토.

## 발표 슬라이드 연결 (5/23)

- **슬라이드 10 (Entity 라벨 품질)** ← **L4 PASS 답변 그대로 + Discovery 3 (CONTAINS 매칭마저 0개)** 보강
- **슬라이드 11 (VectorRAG ↔ GraphRAG 보완)** ← L1 (의도는 Q4 와 답변 차이 였으나 entity 자체 부재로 검증 못함 — Discovery 3 로 대체)
- **슬라이드 13 (NEW: Local Retriever 데모)** ← **L4 데모** (relations=15 + 의미론적 challenge)
- **슬라이드 14 (Routing 명분)** ← **L5 PASS** (글로벌 질의 → Layer C 안내)

## 의존 / 후속

- 의존: ✅ #17 (8문서 적재 완료, 5/16), ✅ #18 (Text2Cypher 패턴 참고, PR #48)
- 후속:
  - **#21** Routing Agent — Q vs L 분기 (키워드 "관계/관련/영향" → Local)
  - **#X (신규)** Entity 추출 LLM 한계 — 회사명 정확 추출 + alias normalization (5/24+ W5 영역)
- 미래: #46 OpenAI 마이그 후 GPT-5-mini 로 비교 측정 / fulltext index 추가
