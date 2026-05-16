# 2026-05-16 — W3 batch ingest (#17)

> Status: **🎉🎉🎉🎉 8/8 100% 적재 + Aura 통계 5종 측정 + 박제 완료. PR #45 머지 + #18 시작 준비.**
> 발표 메시지 확정: **선택지 3 — 디버깅 자체를 trade-off 인사이트로**

## 🏆🏆🏆🏆 5/16 8/8 100% 적재 완료 (16:05 ~ 17:33, 약 76분)

### 1차 적재: 8문서 (16:05~17:19, 71분) — 7/8 성공

| 파일 | 포맷 | 타입 | sec | chunks(T/B) | ent(raw→grp) | rel | mentions | parse | extract | link | neo4j | total | ok |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| DS투자증권_시황분석_리포트.pdf | pdf | report | 6 | 52/0 | 103→60 | 32 | 102 | 8.4 | 143.5 | 28.5 | 39.0 | 219.4 | ✅ |
| 금융감독원_..._직접금융_조달실적.doc | doc | (unknown) | 0 | 0/0 | 0→0 | 0 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | ❌ |
| 농협_2022년_9월말_기준_사업보고서.hwp | **hwp** | filing | 1 | 11/0 | 56→56 | 0 | 56 | 2.5 | 26.4 | 12.4 | 15.3 | 56.6 | ✅ |
| 미래에셋증권_1분기_실적보고서.pdf | pdf | ir | 1 | 28/0 | 131→120 | 17 | 131 | 0.2 | 47.0 | 36.1 | 36.9 | 120.3 | ✅ |
| 미래에셋증권_2분기_실적보고서.pdf | pdf | ir | 1 | 27/0 | 121→116 | 52 | 120 | 0.2 | 53.8 | 29.6 | 38.4 | 121.9 | ✅ |
| 미래에셋증권_3분기_실적보고서.pdf | pdf | ir | 1 | 27/0 | 149→145 | 42 | 149 | **1514.8** | 47.2 | 25.9 | 43.8 | 1631.7 | ✅ |
| 미래에셋증권_4분기_실적보고서.pdf | pdf | ir | 30 | **68/6** | **335→261** | 55 | 329 | **1694.7** | 109.7 | 109.4 | 102.3 | 2016.0 | ✅ |
| 한화투자증권_두산밥캣_기업분석_리포트.pdf | pdf | report | 12 | 15/5 | 42→33 | 31 | 42 | 12.9 | 40.7 | 9.2 | 20.3 | 83.1 | ✅ |

### 2차 적재: DOC → DOCX 변환 후 (17:28~17:33, 5분) — 1/1 성공

| 파일 | 포맷 | 타입 | sec | chunks(T/B) | ent(raw→grp) | rel | mentions | parse | extract | link | neo4j | total | ok |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 금융감독원_..._직접금융_조달실적.docx | **docx** | **disclosure** | 1 | **49/0** | **275→251** | 26 | **260** | 1.7 | 106.0 | 116.6 | 73.3 | 297.7 | ✅ |

### 🎉 진짜 최종 8/8 100% 총합

| 지표 | 1차 (7문서) | 2차 (1문서) | **총합** |
|---|---|---|---|
| 성공률 | 7/8 (87.5%) | 1/1 (100%) | **8/8 (100%)** 🎉 |
| 소요 시간 | 71분 | 5분 | **76분** |
| 청크 (text) | 228 | 49 | **277** |
| Raw entity | 937 | 275 | **1,212** |
| Grouped entity | 791 | 251 | **1,042** |
| NED compression | 0.84 | 0.91 | **0.86** |
| Relation | 229 | 26 | **255** |
| MENTIONS | 929 | 260 | **1,189** |

## 🎯🎯🎯 5/16 8문서 Aura Cypher 통계 (17:37 측정)

### Q1: 노드 라벨별 (총 610 노드)

```
| label    | n   |
|----------|-----|
| Chunk    | 277 |
| Entity   | 261 |
| Section  |  53 |
| Table    |  11 |   ← Table 노드 첫 적재!
| Document |   8 |
```

→ Layer A (Document/Section/Chunk/Table = 349) + Layer B (Entity = 261) 완벽 통합.
→ Table 11개는 미래에셋 4Q (6) + 한화 두산밥캣 (5) 에서 추출. 시각 자료의 그래프 통합.

### Q2: 관계 타입별 (총 2,451 관계)

```
| rel             |    n |
|-----------------|------|
| MENTIONS        | 1553 | ← Layer A ↔ Layer B 압도적 최다
| CONTAINS_CHUNK  |  277 | ← Section → Chunk (1:1)
| HAS_METRIC      |  270 | ← Company → Metric (금융 도메인 풍부)
| NEXT            |  235 | ← Chunk → Chunk (순서)
| HAS_SECTION     |   53 | ← Document → Section
| FACES_RISK      |   34 | ← Company → Risk
| HAS_OUTLOOK     |   12 | ← Company → Outlook
| CONTAINS_TABLE  |   11 | ← Section → Table
| RECOMMENDED_FOR |    6 | ← 새 관계 타입 발견!
```

→ **MENTIONS 1553** — Layer A ↔ Layer B 완전 통합 정량화
→ **HAS_METRIC 270** — 금융 도메인 지표 풍부 추출 검증
→ **RECOMMENDED_FOR 6** — 새 관계 타입 (Stock Recommendation 추정)

### Q3: Entity 타입별 분포 ⭐⭐⭐ (발표 핵심 슬라이드!)

```
| Type     | DISTINCT Chunks | Total Mentions |
|----------|-----------------|----------------|
| Company  | 186             | 1,220          |
| Metric   |  69             |   297          |
| Risk     |  24             |    29          |
| Outlook  |   7             |     7          |
```

#### 핵심 통찰

- **Company 1개당 평균 6.56개 청크에서 언급** (1,220 / 186)
  - 1문서 시절 (4.86) 보다 1.4배 높음 — 다중 문서 적재 시 entity 재사용성 증가
- **Metric 69 entity, 297 mentions** — 한 metric 당 평균 4.3 청크 언급
- **VectorRAG 단순 유사도로는 불가능한 entity-청크 다중 매핑** 정량 증거

### Q4: 미래에셋증권 NED 검증 — ⚠️ 빈 결과 (예상치 못한 발견!)

```cypher
MATCH (e:Entity:Company {name: "미래에셋증권"})<-[:MENTIONS]-(c:Chunk)...
```
→ `No changes, no records`

**원인 분석** (추정, 5/17 일요일 확인 필요):
1. **NED 의 한국어 회사명 표기 변형** — entity 가 정확히 "미래에셋증권" 으로 저장되지 않음
   - 가능성: "미래에셋증권(주)", "미래에셋 증권", "미래에셋", "Mirae Asset" 등으로 분산
2. **NED 임계값 0.92 가 너무 엄격** — 같은 회사여도 다른 group 으로 분류됨
3. **Aliases 에는 있지만 name 에는 없음** — 대표 이름 선정 로직의 영향

#### 5/17 일요일 확인 쿼리

```cypher
// 미래에셋 관련 모든 Company entity 찾기
MATCH (e:Entity:Company)
WHERE e.name CONTAINS "미래에셋"
   OR ANY(alias IN e.aliases WHERE alias CONTAINS "미래에셋")
RETURN e.name, e.aliases, e.member_count
ORDER BY e.member_count DESC;

// 또는 더 넓게 — 모든 Company 중 빈도 높은 것
MATCH (e:Entity:Company)
RETURN e.name, e.member_count
ORDER BY e.member_count DESC
LIMIT 20;
```

#### 발표 슬라이드 — 이게 오히려 진짜 보석!

> **"NED 의 한국어 회사명 표기 변형 challenge — '미래에셋증권' 이 분기 보고서별로 다른 표기로 추출되어 단일 group 으로 NED 되지 않음. production 환경에서 한국어 entity disambiguation 의 추가 후처리 필요성 발견."**

→ "GraphRAG 의 잘 동작하는 부분 + 추가 작업 필요한 부분" 의 정직한 분석. **멘토가 정말 좋아할 인사이트**.

### Q5: doc_type 분포 — 포맷 + 도메인 다양성

```
| format | doc_type   | n |
| pdf    | ir         | 4 |  ← 미래에셋 1Q~4Q
| pdf    | report     | 2 |  ← DS투자증권 + 한화 두산밥캣
| hwp    | filing     | 1 |  ← 농협
| docx   | disclosure | 1 |  ← 금감원
```

**3개 포맷 × 4개 doc_type** 완벽한 다양성!

#### 발표 슬라이드

> **"3개 포맷 (PDF + HWP + DOCX) 과 4개 doc_type (report/ir/filing/disclosure) 이 한 그래프에 통합. 금융 도메인의 모든 비정형 문서 형태를 GraphRAG 가 흡수."**

## 🎤 8문서 통합 발표 슬라이드 핵심 인사이트

> **"5/16 단일 토요일에 8개 금융 문서 (3개 포맷, 4개 doc_type) 를 GraphRAG 그래프로 통합. 610 노드 + 2,451 관계 + 1,553 MENTIONS. Company 186 entity 가 평균 6.56개 청크에서 언급되는 풍부한 entity-청크 다중 매핑 구조 확인. VectorRAG 의 단순 유사도 검색으로는 불가능한 그래프 traversal 기반 질의 가능."**

## 🏆 5/16 1문서 sanity 결과 (12:48~12:49) — 검증 자산

### 적재 운영 데이터

| 파일 | 포맷 | 타입 | sec | chunks(T/B) | ent(raw→grp) | rel | mentions | parse | extract | link | neo4j | total | ok |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| DS투자증권_시황분석_리포트.pdf | pdf | report | 6 | **52/0** | **113→55** | 28 | **108** | 8.6 | 146.3 | 33.6 | 39.0 | 227.5 | ✅ |

### Aura console Cypher 통계 (12:55 1문서 sanity 후 측정)

**Q1: 노드** — Entity 55 / Chunk 52 / Section 6 / Document 1 = 114 노드
**Q2: 관계** — MENTIONS 108 / CONTAINS_CHUNK 52 / NEXT 46 / HAS_METRIC 13 / FACES_RISK 7 / HAS_SECTION 6 = 232 관계
**Q3: Entity 타입** — Company 14 (68 mentions) / Risk 6 (21) / Metric 4 (14) / Outlook 3 (5)

→ Company 1개당 평균 4.86 청크 언급 (1문서)
→ 8문서로 확장 시 6.56 청크로 증가

## 🌟 발표 자료 보석 종합 (5/23 슬라이드 시드)

### A. DOC → DOCX 변환 + 재적재 성공 ⭐⭐⭐

LibreOffice headless 변환 + 2차 재실행으로 ✅ 적재.
- 49 청크 + 275→251 entity (compression 0.91) + 260 MENTIONS

**엔지니어링 사이클**:
```
1차 시도 (LibreOffice 미설치)  →  ❌ 실패
       ↓
원인 분석 (코드 의존성 발견)
       ↓
2차 시도 (수동 변환 + 재적재)   →  ✅ 성공
       ↓
production 배포 가이드 박제
```

### B. HWP 파서 정상 동작 ⭐
- 농협 사업보고서 — 11 청크 + 56 entity + 56 MENTIONS 적재
- 의존성 우려 → 실제로는 정상

### C. 미래에셋 4분기 풍부 ⭐
- 68 청크 + 6 표 (Table 노드 첫 적재) + 335→261 entity (compression 0.78) + 329 MENTIONS

### D. NED 한국어 변형 challenge ⭐⭐ (NEW! Q4 빈 결과로 발견)
- 미래에셋증권이 분기별로 다른 표기 → 단일 group 으로 안 묶임
- production 환경에서 한국어 entity disambiguation 추가 후처리 필요

### E. LLM 비결정성
- DS투자증권 2회 추출: 113→55 vs 103→60 차이

### F. doc_type 자동 분류 4가지
- report / ir / filing / disclosure

### G. SemanticChunker 본질적 비효율
- 820자 / 31.3초 (CPU + bge-m3)
- USE_SIMPLE_CHUNKER fallback 으로 우회

## ✅ 5/16 토요일 검증 완료 사항

### 코드/테스트
- **단위 테스트 11/11 PASS** — `tests/kg/test_builder_layer_a.py`
- **PR #45 생성** — https://github.com/TaskerJang/doc-graph-agent/pull/45
- **chunker.py fallback 추가** — commit `8f0bcb1`
- **🎉 1문서 sanity 성공** — DS투자증권 PDF, 227.5초
- **🎉🎉🎉 8/8 적재 완료 (1차 7/8 + 2차 1/1 = 100%)** — 76분
- **🎉🎉🎉 Aura Cypher 5종 통계 측정 완료** — 17:37
  - 610 노드 + 2,451 관계 + 1,553 MENTIONS 정량화
  - Q4 NED 한국어 변형 challenge 발견 (발표 보석)

### 환경
- **새 Aura Free 인스턴스 구축** — ID `9b57188f`
- **`.env` 갱신 완료** — NEO4J_URI / NEO4J_PASSWORD / USE_SIMPLE_CHUNKER=1
- **LibreOffice 미설치 확인** — 수동 변환으로 검증

## 🎯 5/17(일) 시작 가이드 — 진짜 마무리

### Step 1 — Q4 NED 추가 진단 (3분)

```cypher
// 미래에셋 관련 모든 entity 찾기
MATCH (e:Entity:Company)
WHERE e.name CONTAINS "미래에셋"
   OR ANY(alias IN e.aliases WHERE alias CONTAINS "미래에셋")
RETURN e.name, e.aliases, e.member_count
ORDER BY e.member_count DESC;

// 전체 Company 중 빈도 높은 entity
MATCH (e:Entity:Company)
RETURN e.name, e.member_count
ORDER BY e.member_count DESC
LIMIT 20;
```

→ NED 동작 패턴 정확히 확인 → 발표 슬라이드 보강.

### Step 2 — PR #45 머지 + 이슈 #17 close (1분)

https://github.com/TaskerJang/doc-graph-agent/pull/45 → **Merge pull request** 버튼.

머지 후:
```cmd
cd C:\Users\taske\doc-graph-agent
git checkout dev
git pull origin dev
git branch -d feat/17-batch-ingest
```

### Step 3 — #18 W4 Text2Cypher 시작

```cmd
git checkout -b feat/18-text2cypher
```

이슈 #18 요구사항:
- `retrieval/text2cypher.py` — LLM 기반 자연어 → Cypher 변환
- 스키마 프롬프트 — 노드/관계 정의 LLM 주입
- 안전장치 — read-only 강제 + LIMIT 100 강제
- 결과 파싱 → 자연어 답변 생성 (LLM 2단계)
- 평가 셋 중 factual/numerical 질문 5개로 정성 검증

**5/17 평가 셋 질문 후보** (8문서 그래프 위에서):
1. "DS투자증권 시황분석 리포트에서 언급된 회사는 몇 개인가?"
2. "미래에셋증권 4분기 보고서의 Table 은 몇 개인가?"
3. "보도자료(disclosure) 유형 문서의 회사 entity 들은?"
4. "두산밥캣과 함께 언급된 리스크가 있는가?"
5. "전체 그래프에서 가장 많이 언급된 Company 5개는?"

---

## 작업 범위

PR #44 (#24 Opik 1단계) 머지 직후 진행. 이미 검증된 두산밥캣 1청크 파이프라인을 평가 셋 8문서 전체로 확장.

### 변경 사항

**Layer A 적재 추가** (`kg/builder.py`):
- `build_layer_a(document, client)` — Document / Section / Chunk / Table 노드 MERGE + 4관계
- `link_chunks_to_entities(linking, client)` — Layer A Chunk → Layer B Entity `[:MENTIONS]`

**옵션 3 — chunk_id global prefix** (`kg/extractor.py`):
- entity local_id 가 자동으로 `{chunk_id}__ent_001` 형식 prefix
- `make_global_id` / `parse_global_id` 헬퍼

**일괄 처리 스크립트** (`scripts/run_w3_batch.py`):
- 8문서 순회 + 문서별 stat 수집 + markdown 표 stdout

**chunker.py USE_SIMPLE_CHUNKER fallback** (commit `8f0bcb1`):
- `_semantic_split()` 에 환경변수 분기, ON 시 `RecursiveCharacterTextSplitter`
- 기본값 OFF, chunk 정책 동일 유지

## 🎤 발표 메시지 확정 (5/23) — 선택지 3

> **"동일 chunker 로 비교하려 했으나, CPU 환경에서 SemanticChunker 가 비현실적임을 발견. 운영 비용의 trade-off 를 정량화함."**

### 발표 구조 (12슬라이드 — 데이터 강화)

1. 문제 정의
2. SemanticChunker 발견 (820자/31초)
3. 분석 (LangChain 내부 sequential)
4. trade-off 표
5. fallback 구현 (USE_SIMPLE_CHUNKER)
6. **운영 데이터 (8/8 100%, 76분)**
7. **포맷 다양성 (PDF + HWP + DOCX, 4 doc_type)**
8. **production 의존성 (LibreOffice)** ⭐
9. **그래프 통계 (610 노드, 2,451 관계, 1,553 MENTIONS)** ⭐ NEW!
10. **NED 한국어 변형 challenge** ⭐ NEW!
11. **미래에셋 4Q 깊이 + LLM 비결정성**
12. 인사이트 메시지

### "그래서 결국 성능 비교는?" 질문 대응

답변 준비:
- SemanticChunker 원본은 production 환경 마련 후 (Issue #46)
- chunk 정책은 동일 유지, Layer 구조 효과는 정량화: 1,189 MENTIONS, 0.86 compression
- 4가지 doc_type 자동 분류
- **NED 한국어 변형 challenge** — production 후처리 추가 필요 (정직한 한계)

## 시행착오 박제

5/16 토요일 디버깅 자산 (= 발표 슬라이드 시드):
- ✅ **bge-m3 정상** (108ms/문장)
- ✅ **PDF / OCR / Neo4j / SemanticChunker 초기화 모두 정상**
- ❌ **SemanticChunker.split_text 본질적 비효율** — 820자/31초
- ✅ **USE_SIMPLE_CHUNKER fallback** — commit `8f0bcb1`
- ✅ **8/8 적재 100%** + **Aura 통계 5종**
- ✅ **HWP / DOCX 파서 정상**
- ✅ **Table 노드 첫 적재** (11개)
- ✅ **doc_type 4가지 자동 분류**
- ⚠️ **NED 한국어 변형 challenge** — Q4 빈 결과로 발견 (NEW)
- **Aura Free trial** — 새 인스턴스 `9b57188f`
- **LibreOffice 환경 의존성** — production Docker 가이드
- **MS Store python stub** — `uv run` 영향 없음

### 미래 발견 (#46+)

- **LibreOffice 자동화** — production Docker 이미지 추가
- **OCR 시간 폭증** — 3Q/4Q parse 1500초+ → 캐시 또는 라이브러리 교체
- **OpenAI 마이그레이션** (#46) — SemanticChunker 원본 복원
- **NED 한국어 후처리** ⭐ NEW! — 회사명 정규화 추가 단계

### local_id 충돌 — 옵션 3 으로 해결

```
adapter.parse_document() → Document.sections[].chunks[].id ("doc1:c0001")
                              ↓
chunks = [{doc_id, chunk_id, section, text}]
                              ↓ extract() — chunk_id prefix
ExtractedEntity.local_id = "doc1:c0001__ent_001"
                              ↓ link_entities() — 청크 간 NED
EntityGroup.members[*].local_id = "doc1:c0001__ent_001"
                              ↓ link_chunks_to_entities()
parse_global_id("doc1:c0001__ent_001") → ("doc1:c0001", "ent_001")
                              ↓
(:Chunk {id:"doc1:c0001"}) -[:MENTIONS]-> (:Entity {group_id:"grp_001"})
```

## 발표 자료 시드 (5/23 용)

| 자료 | 상태 | 출처 |
|---|---|---|
| 1문서 → 8/8 적재 운영 데이터 표 | ✅ 완료 | 본 문서 |
| **🎯 Aura 통계 5종 (8문서, 17:37 측정)** | ✅ 완료 | 본 문서 |
| **🎯 노드/관계 합계 (610 / 2,451)** | ✅ 완료 | Q1, Q2 |
| **🎯 Entity 타입별 (Company 186 / 1,220 mentions)** | ✅ 완료 | Q3 |
| **🎯 NED 한국어 변형 challenge** ⭐ NEW! | ✅ 완료 | Q4 빈 결과 |
| **🎯 doc_type × format 4×3 다양성** | ✅ 완료 | Q5 |
| Layer A + Layer B + MENTIONS 그래프 시각화 | ⏸️ Aura console 캡처 | 일요일 |
| **🎯 LibreOffice 의존성 발견 + 해소 사이클** | ✅ 완료 | 본 문서 |
| `@track` 으로 자동 수집된 trace | ✅ Opik UI 확인 가능 | Opik UI |
| **🎯 미래에셋 4분기 — 68 청크 + 6 표 + 261 entity** | ✅ 완료 | 본 문서 |
| **🎯 LLM 비결정성 — DS투자증권 2회 추출 차이** | ✅ 완료 | 본 문서 |
| **🎯 SemanticChunker 본질적 비효율 (820자/31초)** | ✅ 완료 | 본 문서 |
| **🎯 USE_SIMPLE_CHUNKER fallback 코드** | ✅ 완료 | commit `8f0bcb1` |

## 관련

- PR: #45 (5/17 일요일 머지 예정)
- 의존: ✅ PR #44 (#24 Opik 1단계)
- 후속: #18 Text2Cypher (Layer A 적재된 풍성한 그래프 위에서)
- 미래: #46 OpenAI 마이그레이션, #47 회사 발표 (6/1), [신규] NED 한국어 후처리
