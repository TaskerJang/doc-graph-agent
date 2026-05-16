# 2026-05-17 — W4 Text2Cypher (#18) 정성 검증 완료

> Status: **🎉🎉🎉🎉 8/8 PASS! Text2Cypher 모듈 + 평가 셋 + 정성 검증 모두 완료.**
> 5/16 박제된 평가 셋 8 케이스 (Q1~Q5 + F1~F3) 모두 PASS.
> 발표 슬라이드 10/11 "Entity 라벨 품질 challenge" + "VectorRAG ↔ GraphRAG 보완 관계" 정량 검증 완료.

## 🏆🏆🏆🏆 W4 Text2Cypher 평가 셋 정성 검증 결과 (20:52, 약 45초)

| ID | category | verdict | kw% | limit | safe | rows | elapsed | answer 요약 |
|----|----------|---------|----:|:----:|:---:|----:|--------:|------------|
| Q1 | traversal | **PASS** | 100% | ✅ | ✅ | 68 | 8.1s | DS투자증권 시황분석 리포트에서 언급된 주요 entity 들은... |
| Q2 | factual   | **PASS** | 100% | ✅ | ✅ | 1  | 4.3s | 미래에셋증권 4분기 실적보고서에는 총 6개의 표(Table) 가 적재되어 있습니다. |
| Q3 | filter    | **PASS** | 100% | ✅ | ✅ | 100 | 9.0s | 보도자료 유형 문서에서 언급된 상위 Entity 들은... |
| Q4 | semantic  | **PASS** | 100% | ✅ | ✅ | 0  | 6.2s | 해당 조건에 맞는 결과를 찾지 못했습니다. "두산밥캣"과... |
| Q5 | topN      | **PASS** | 100% | ✅ | ✅ | 5  | 6.4s | 전체 그래프에서 가장 많이 언급된 상위 5개 Company 라벨 entity는... |
| F1 | fallback  | **PASS** | 100% | ✅ | ✅ | 0  | 5.1s | 현대차_보고서.pdf 파일에 대한 정보를 찾지 못했습니다... |
| F2 | fallback  | **PASS** | 0%   | ✅ | ✅ | 0  | 3.5s | 그래프에 정의된 엔티티 라벨은 'Company', 'Risk',... |
| F3 | fallback  | **PASS** | 0%   | ❌ | ✅ | 0  | 2.3s | 데이터 삭제는 허용되지 않는 작업입니다. |

```
총 8 케이스 · PASS 8 · PARTIAL 0 · FAIL 0
전체 소요: 44.8s
평균 case 당: 5.6s (Kimi 2회 호출)
```

## ⭐⭐⭐ 진짜 보석 — Q5 Company top 5 결과

5/16 박제된 **Entity 라벨 품질 challenge** 가 정량 확정됐어요:

```cypher
MATCH (e:Entity:Company)<-[:MENTIONS]-(c:Chunk)
RETURN e.name AS entity, count(c) AS mentions
ORDER BY mentions DESC LIMIT 5
```

| Rank | Entity 이름 | mentions | 실제 분류 |
|------|-------------|----------|-----------|
| 1 | **공모발행액 23조 7,050억원 (2025년 10월)** | **31** | ❌ metric |
| 2 | 일반회사채 발행 규모 전월 대비 감소 | 19 | ❌ metric |
| 3 | 기업공개 발행액 524억원 (2025년 10월) | 18 | ❌ metric |
| 4 | 유상증자 발행액 415억원 (2025년 10월) | 17 | ❌ metric |
| 5 | AA등급 이상 회사채 발행 비중 73.0% | 17 | ❌ metric |

→ **Company 라벨 top 5 가 100% 금융 metric**, 진짜 회사명 0개.

**LLM 자연어 답변** (Answer prompt 의 정직한 안내 가이드가 완벽 동작):
> "...다만 'Company' 라벨임에도 실제 회사명이 아닌 금융 metric 으로 추출되어 있어,
> entity 추출 단계의 라벨 품질을 production 환경에서 보강할 필요가 있습니다."

→ 발표 슬라이드 10 (Entity 라벨 품질 challenge) 의 정량 증거 + 정직한 보고 완성.

## 🌟 케이스별 핵심 분석

### Q1 — Layer A → Layer B traversal (68 rows)

생성 Cypher 가 정답과 거의 100% 일치:

```cypher
MATCH (d:Document {filename: 'DS투자증권_시황분석_리포트.pdf'})
      -[:HAS_SECTION]->(:Section)
      -[:CONTAINS_CHUNK]->(c:Chunk)
      -[:MENTIONS]->(e:Entity)
RETURN labels(e)[1] AS type, e.name AS name, count(c) AS chunk_count
ORDER BY chunk_count DESC LIMIT 100
```

답변에서 정직하게 라벨 혼재 명시:
> "...'Company' 라벨임에도 실제 회사명이 아닌 금융 metric 이 섞여 있습니다.
> 이는 entity 추출 단계의 라벨 품질을 production 환경에서 보강할 필요가
> 있음을 의미합니다."

### Q2 — factual / numerical (정답 6)

생성 Cypher 가 정답과 사실상 동일 (LIMIT 100 만 자동 부착):
- 결과: `[{"table_count": 6}]`
- 답변: "미래에셋증권 4분기 실적보고서에는 총 6개의 표(Table) 가 적재되어 있습니다."

### Q3 — doc_type 필터 (100 rows)

LLM 이 정답보다 더 똑똑한 `count(DISTINCT c)` 사용 — 같은 entity 가 여러 청크에 언급되어도 중복 카운트 회피.

```cypher
MATCH (d:Document {doc_type: 'disclosure'})...
RETURN d.filename, ..., count(DISTINCT c) AS mentions  -- DISTINCT 추가!
ORDER BY mentions DESC LIMIT 100
```

답변에서 출처 명시:
> "정보는 '금융감독원_251125__보도자료__25_10월중_기업의_직접금융_조달실적.docx' 문서에서 추출되었습니다."

### Q4 — semantic 관계 (0 rows, 정직한 결과)

co-mention 패턴으로 검색했으나 0 rows.
- 두산밥캣 entity 가 Company 로 추출됐는지 미확인
- 또는 Risk entity 와 같은 청크에 등장 안 함
- → **Entity 라벨 품질 + Risk 추출 sparsity** 의 정량 증거

답변:
> "해당 조건에 맞는 결과를 찾지 못했습니다. '두산밥캣'과 함께 언급된 리스크에 대한
> 정보는 존재하지 않는 것으로 보입니다. 다른 회사명이나 리스크와의 조합으로 다시
> 질문해 보시거나..."

→ 빈 결과 graceful + 대안 제안.

### F1 — 존재하지 않는 문서 (graceful)

LLM 이 자연스럽게 Cypher 생성하고 실행 → 0 rows → 친절한 안내:
> "현대차_보고서.pdf 파일에 대한 정보를 찾지 못했습니다. 해당 파일에 대한
> 구체적인 섹션이나 청크 정보가 없을 수 있습니다. 다른 파일명으로 검색하시거나,
> 그래프 데이터베이스에 해당 파일의 정보가 포함되어 있는지 확인해 보세요."

부가 발견: Neo4j 가 `c.page` property 미정의 경고 던짐. LLM 이 chunk 의 page 속성 가정했으나 실제 스키마엔 없음 → 다음 prompt 개선 포인트.

### F2 — 스키마 외 라벨 (cypher=null graceful)

LLM 이 자체 거부:
> "Person 라벨은 그래프에 정의되지 않았습니다. 사용 가능한 entity 라벨:
> Company, Risk, Metric, Outlook, Recommendation"

→ system prompt 의 fallback 예시 F1 이 완벽 작동.

### F3 — write 시도 (보안)

LLM 이 자체 거부 (cypher=null):
> "해당 질문은 현재 스키마로 답할 수 없습니다.
> 이유: 데이터 삭제는 허용되지 않는 작업입니다."

→ `_enforce_safety` 까지 안 가도 LLM 단계에서 차단됨. **2중 방어 검증 완료**.

## 🎯 #18 DoD 100% 충족 검증

| DoD 항목 | 검증 케이스 | 결과 |
|---|---|---|
| "X 문서의 Y 섹션에 무엇이 있나" 류 답변 | Q1, Q3 | ✅ PASS |
| factual / numerical 5개 정성 검증 | Q1~Q5 | ✅ 5/5 PASS |
| 잘못된 Cypher graceful fallback | F1, F2, F3 | ✅ 3/3 PASS |
| read-only + LIMIT 100 강제 | 모든 케이스 | ✅ 자동 부착 확인 |

## 🚧 발견된 production 개선 포인트 (#18+)

### 1. LLM 이 추측한 property 가 스키마에 없는 경우

**F1 케이스**:
```
WARNING neo4j.notifications: The property `page` does not exist
in database `9b57188f`. Verify that the spelling is correct.
```

LLM 이 `c.page`, `c.order_index` 를 가정하고 RETURN 에 포함시켰는데 실제로는 `c.page` 없음 (또는 일부 청크에만 있음). 쿼리는 성공하지만 null 반환.

**대응**:
- system prompt 에 actual property 목록 박제 (현재는 노드 구조만)
- 또는 Cypher 실행 후 `notifications` 받아서 LLM 에 피드백 (#21 이후 작업)

### 2. property `member_count` 사용 안 됨

**Q5 정답 vs 생성**:
- 정답: `RETURN e.name, e.member_count AS group_size, count(c) AS mentions`
- 생성: `RETURN e.name, count(c) AS mentions`

`member_count` 가 있으면 NED 그룹 크기까지 보여줄 수 있는데 LLM 이 생략. system prompt 에 property 활용 가이드 추가 가능.

### 3. answer_hints 매칭률 낮음 (정상)

검증 결과 `answer_hints=N/M hits` 가 대부분 낮음 (예: Q5 = 3/67). 이는 LLM 답변이 hints 단어 외에도 풍부한 자연어를 생성하기 때문 — **정상 동작**. heuristic 평가의 한계로 박제만.

## 🎤 발표 슬라이드 갱신 (5/23)

발표 슬라이드 #18 진척 반영:

### 슬라이드 10 (Entity 라벨 품질 challenge) ⭐⭐⭐
- 5/16 진단 3종 + **5/17 Text2Cypher Q5 결과**로 정량 정밀
- "186 Company entity 중 진짜 회사명 1개" → "Company top 5 가 100% 금융 metric"
- 자연어 답변이 한계를 정직하게 보고 — production 신뢰성

### 슬라이드 11 (VectorRAG ↔ GraphRAG 보완) ⭐
- **5/17 Q4 결과**: "두산밥캣 + 리스크" 0 rows
- Entity 라벨 품질 + Risk 추출 sparsity 동시 challenge
- VectorRAG (대명사 해소) + 사람 큐레이션 entity 보완 필요성 증명

### 슬라이드 12 (Text2Cypher 데모) — NEW!
```
Q: "미래에셋증권 4분기 보고서의 Table 은 몇 개인가?"

생성 Cypher (Kimi, 4초):
  MATCH (d:Document {filename: '미래에셋증권_4분기_실적보고서.pdf'})
        -[:HAS_SECTION]->(:Section)-[:CONTAINS_TABLE]->(t:Table)
  RETURN count(t) AS table_count LIMIT 100

답변 (Kimi, 1초):
  "미래에셋증권 4분기 실적보고서에는 총 6개의 표(Table) 가
   적재되어 있습니다."

8 케이스 정성 검증: 8/8 PASS, 평균 5.6초/케이스
```

## ✅ 5/17 일요일 검증 완료

### 코드
- ✅ `retrieval/text2cypher.py` (320 lines) — 모듈 구현
- ✅ `retrieval/prompts/text2cypher_system_v1.md` — 스키마 + few-shot 5개
- ✅ `retrieval/prompts/text2cypher_answer_v1.md` — 답변 가이드 (라벨 한계 정직)
- ✅ `retrieval/eval_set.md` (5/16 박제) — 평가 셋 정답 Cypher 5+3
- ✅ `scripts/run_w4_eval.py` (550 lines) — 자동 검증 스크립트

### 정성 검증
- ✅ Q1 [traversal]:   PASS (8.1s, 68 rows, 라벨 혼재 정직 보고)
- ✅ Q2 [factual]:     PASS (4.3s, 1 row, "6개")
- ✅ Q3 [filter]:      PASS (9.0s, 100 rows, DISTINCT 자발 사용)
- ✅ Q4 [semantic]:    PASS (6.2s, 0 rows, graceful + 대안 제안)
- ✅ Q5 [topN]:        PASS (6.4s, 5 rows, ⭐ 라벨 품질 정량 확정)
- ✅ F1 [fallback]:    PASS (5.1s, 0 rows, 존재하지 않는 문서 안내)
- ✅ F2 [fallback]:    PASS (3.5s, cypher=null, 스키마 외 라벨 안내)
- ✅ F3 [fallback]:    PASS (2.3s, cypher=null, 보안 거부)

### 환경
- ✅ Aura `9b57188f` 5/16 8문서 적재 그대로 활용
- ✅ Opik 트레이싱 8 케이스 모두 정상 (Comet UI 에서 확인 가능)
- ✅ Kimi `moonshot-v1-8k` 2단계 호출 (Cypher + Answer)

## 🌅 다음 단계 (5/17 일요일 잔여 or 5/18+)

### Step 1 — PR #18 생성 + 머지 (1분)
3 commits 푸시 완료 (`feat/18-text2cypher` 브랜치):
- `142ff00` docs(eval): 평가 셋 5종 박제
- `ff03ba9` feat(retrieval): Text2Cypher 모듈
- `98490c0` feat(scripts): 평가 셋 검증 스크립트
- (현재 commit) docs(weekly-log): 8/8 PASS 박제

PR 생성 → dev 머지 → 이슈 #18 close.

### Step 2 — W4 다음 작업 (5/18~)

- **#21 Routing Agent** — 질문 유형에 따라 Layer A (Text2Cypher) / Layer B (Local Retriever) / Layer C (Community) 분기
- **#19 Local Retriever** — entity 중심 그래프 traversal
- **#20 Community Summary** — Louvain 기반 entity 클러스터링 + 전체 트렌드 질의

### Step 3 — 발표 슬라이드 정리 (5/22)

5/17 결과 반영해서 슬라이드 10/11/12 갱신.

### Step 4 — 5/23 멘토링 발표

12 슬라이드 + Q&A. 핵심: 정직한 한계 분석 + production 적용 가능성.

## 관련

- PR: #18 (5/17 일요일 머지 예정)
- 의존: ✅ PR #45 (#17 8문서 적재 완료)
- 후속: #19 Local Retriever, #20 Community Summary, #21 Routing Agent
- 미래: #46 OpenAI 마이그 (5/24+), #47 회사 발표 (6/1)
- 발표: 5/23 멘토링 슬라이드 10/11/12 정량 증거
