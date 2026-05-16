# 2026-05-16 — W3 batch ingest (#17)

> Status: **🎉 1문서 sanity + Aura 통계 확인 모두 성공! 8문서 풀 실행만 5/17(일) 으로 이월.**
> 발표 메시지 확정: **선택지 3 — 디버깅 자체를 trade-off 인사이트로**

## 🏆 5/16 1문서 sanity 결과 (12:48~12:49)

### 적재 운영 데이터

| 파일 | 포맷 | 타입 | sec | chunks(T/B) | ent(raw→grp) | rel | mentions | parse | extract | link | neo4j | total | ok |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| DS투자증권_시황분석_리포트.pdf | pdf | report | 6 | **52/0** | **113→55** | 28 | **108** | 8.6 | 146.3 | 33.6 | 39.0 | 227.5 | ✅ |

**1문서 → 약 4분, 8문서 추정 약 30분**.

### Aura console Cypher 통계 (12:55 실측)

**Q1: 노드 라벨별** (총 114 노드)
```
| label    | n  |
|----------|----|
| Entity   | 55 |
| Chunk    | 52 |
| Section  | 6  |
| Document | 1  |
```
→ Layer A (Document/Section/Chunk = 59) + Layer B (Entity = 55) 완벽 통합

**Q2: 관계 타입별** (총 232 관계)
```
| rel             | n   |
|-----------------|-----|
| MENTIONS        | 108 | ← Layer A ↔ Layer B
| CONTAINS_CHUNK  | 52  | ← Section → Chunk
| NEXT            | 46  | ← Chunk → Chunk
| HAS_METRIC      | 13  | ← Company → Metric
| FACES_RISK      | 7   | ← Company → Risk
| HAS_SECTION     | 6   | ← Document → Section
```
→ Layer A 구조(104) + Layer B 의미(20) + 통합 MENTIONS(108)

**Q3: Entity 타입별 분포** ⭐ (발표 핵심 슬라이드)
```
| Type     | DISTINCT chunks | mentions |
|----------|-----------------|----------|
| Company  | 14              | 68       |
| Risk     | 6               | 21       |
| Metric   | 4               | 14       |
| Outlook  | 3               | 5        |
```
→ **Company 14 entity 평균 4.86 청크 언급** — NED 효과 정량화
→ 1쪽 시황분석에 **14개 회사 + 6개 리스크 + 4개 지표 + 3개 전망** 완전 추출

### 핵심 지표

- ✅ **NED compression 0.49** — 113 raw → 55 group (51% 중복 제거)
- ✅ **Layer A 적재** — Document 1 + Section 6 + Chunk 52 + NEXT 46 (18.47s)
- ✅ **Layer B 적재** — Entity 55 + Relations 28, dropped=0 (8.96s)
- ✅ **MENTIONS 적재** — 108개 (Layer A ↔ Layer B 완전 연결, 11.59s)
- ✅ **Opik trace 자동 수집** — POST 204 No Content 다회 (@track 데코레이터 정상)
- ✅ **chunker fallback 동작 확인** — `USE_SIMPLE_CHUNKER=1` 정상 동작
- ✅ **Aura Cypher 통계 4종 확인** — 노드/관계/엔티티 타입별 모두 박제

### 검증된 PR #45 핵심 기능

1. **옵션 3 (chunk_id global prefix)** — 52개 청크에서 각각 `ent_001~` 가 충돌 없이 `{chunk_id}__ent_001` 로 prefix. linker 가 113→55 그룹화 + MENTIONS 108 매핑 성공.
2. **Layer A `build_layer_a()`** — doc-ontology.md §3 스키마 그대로 (Document/Section/Chunk/Table 4 노드 + 4 관계).
3. **Layer A ↔ Layer B `link_chunks_to_entities()`** — `parse_global_id` 역추적 후 MENTIONS 적재 정상.
4. **Opik `@track`** — extract / link / build_layer_a / link_chunks_to_entities 모든 함수 trace 가 Comet 백엔드에 자동 박힘.

### 🎤 발표 슬라이드 핵심 인사이트 (Aura 통계 기반)

> **"DS투자증권 1쪽 시황분석 리포트 → 14개 회사 + 6개 리스크 + 4개 지표 + 3개 전망. NED compression 0.49 로 entity 중복 51% 제거. Company 1개당 평균 4.86개 청크에서 언급 — VectorRAG 의 단순 유사도 검색으로는 못 얻는 다중 청크 entity 그래프 구조 확인."**

## 🎯 5/17(일) 시작 가이드 (컨텍스트 복구 0초)

### Step 1 — git pull (1분)

```cmd
cd C:\Users\taske\doc-graph-agent
git checkout feat/17-batch-ingest
git pull origin feat/17-batch-ingest
```

(`.env` 의 `USE_SIMPLE_CHUNKER=1` 은 이미 5/16 에 추가됨)

### Step 2 — 8문서 풀 실행 (약 30분)

1문서당 약 4분 × 8 = **약 30분**.

```cmd
uv run python -u -m scripts.run_w3_batch
```

기다리면서:
- 멘토링 책 작업 / 휴식 / 점심
- Opik UI 에서 trace 실시간 확인

### Step 3 — Aura Cypher 통계 확인 (3분)

```cypher
// 노드 라벨별
MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC;

// 관계 타입별
MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS n ORDER BY n DESC;

// Layer A → Layer B 연결 확인
MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
RETURN labels(e)[1] AS type, count(DISTINCT c) AS chunks, count(e) AS mentions
ORDER BY mentions DESC LIMIT 10;

// 미래에셋증권 NED 검증 — 4분기 문서 4개에서 같은 entity 그룹화 됐는지
MATCH (e:Entity:Company {name: "미래에셋증권"})<-[:MENTIONS]-(c:Chunk)<-[:CONTAINS_CHUNK]-(s:Section)<-[:HAS_SECTION]-(d:Document)
RETURN DISTINCT d.filename;
```

결과 캡처 → 본 문서 "그래프 통계 — 8문서" 섹션 박제.

### Step 4 — 결과 박제 + PR 머지

- stdout 의 markdown 표 → 본 문서 "8문서 일괄 적재 결과" 섹션
- Opik UI 스크린샷 → 발표 자료 폴더
- 새 시행착오 (HWP/DOC/큰 PDF) 발견되면 본 문서 시행착오 박제
- **PR #45 머지 + 이슈 #17 close**

### Step 5 — #18 W4 Text2Cypher 시작

Layer A + Layer B + MENTIONS 적재된 풍성한 그래프 위에서.

---

## 작업 범위

PR #44 (#24 Opik 1단계) 머지 직후 진행. 이미 검증된 두산밥캣 1청크 파이프라인을 평가 셋 8문서 전체로 확장.

### 변경 사항

**Layer A 적재 추가**:
- `kg/builder.py` — `build_layer_a(document, client)` 함수 신규
  - Document / Section / Chunk / Table 노드 MERGE (doc-ontology.md §3 스키마)
  - HAS_SECTION / CONTAINS_CHUNK / CONTAINS_TABLE / NEXT 관계 (§4)
  - 4 노드 모두 `id` 유일 제약 추가
- `kg/builder.py` — `link_chunks_to_entities(linking, client)` 함수 신규
  - Layer A Chunk → Layer B Entity `[:MENTIONS]` 관계

**옵션 3 — chunk_id global prefix**:
- `kg/extractor.py` — chunk dict 에 옵셔널 `chunk_id` 키 인식
- entity local_id 가 자동으로 `{chunk_id}__ent_001` 형식으로 prefix
- `make_global_id` / `parse_global_id` 헬퍼 — MENTIONS 매핑에서 역추적
- 5/10 1청크 sanity (chunk_id 없음) 와 호환 — graceful drop

**일괄 처리 스크립트**:
- `scripts/run_w3_batch.py` — eval/dataset/documents/ 의 8문서 순회
- 문서별 stat 수집 → markdown 표 stdout
- `@track` 부착된 함수들이 Opik UI 에 자동 기록

**chunker.py USE_SIMPLE_CHUNKER fallback** (commit `8f0bcb1`):
- `ingestion/chunker.py` 의 `_semantic_split()` 에 환경변수 분기 추가
- ON 시 `RecursiveCharacterTextSplitter` (separators 한국어 친화) 사용
- 기본값 OFF — 회사 레포 동일 동작 유지
- chunk 정책 (size=700, overlap=200, min=50) 은 회사 레포와 동일

## ✅ 5/16 토요일 검증 완료 사항

### 코드/테스트
- **단위 테스트 11/11 PASS** — `tests/kg/test_builder_layer_a.py`
- **옵션 3 prefix 로직 검증** — round-trip + chunk_id 내부 `_` 충돌 케이스 통과
- **PR #45 생성** — https://github.com/TaskerJang/doc-graph-agent/pull/45
- **chunker.py fallback 추가** — commit `8f0bcb1`
- **🎉 1문서 sanity 성공** — DS투자증권 PDF, 227.5초 (위 결과 표)
- **🎉 Aura Cypher 통계 4종 확인 완료** — 위 Q1~Q3 박제

### 환경
- **새 Aura Free 인스턴스 구축** — ID `9b57188f` (기존 trial expired 후 재생성)
- **`.env` 갱신 완료** — 새 NEO4J_URI / NEO4J_PASSWORD / USE_SIMPLE_CHUNKER=1

### 진단 (1.5시간 디버깅 결과)

| # | 검증 대상 | 결과 | 결론 |
|---|---|---|---|
| 1 | bge-m3 50문장 (batch=32) | **5.4초** | ✅ 정상 (문장당 108ms) |
| 2 | PDF 텍스트 추출 (PyMuPDF) | **0.1초/4464자** | ✅ 정상 |
| 3 | Neo4j 새 Aura connectivity | OK | ✅ 정상 |
| 4 | OCR 캐시 | 즉시 hit | ✅ 정상 |
| 5 | SemanticChunker 초기화 | 로그 떴음 | ✅ 정상 |
| 6 | **SemanticChunker.split_text(820자)** | **31.3초** | ❌ **확정 범인** |

→ 6번이 본질적 한계. **LangChain SemanticChunker 는 임베딩을 sequential (batch 안 씀) 호출하므로 CPU + 무거운 모델 조합 비현실적**.

### 부가 발견

**Aura Free trial 정책**
- 기존 인스턴스 "Trial expired" 상태로 전환 → console UI Extend 버튼이 유료 Professional 신용카드 입력 강제
- 해결: 기존 인스턴스 폐기 + 새 Free 인스턴스 생성 (`9b57188f`)
- 14일 후 또 만료 가능성 있음

**MS Store python stub PATH 에 있음**
```
where python → C:\Users\taske\AppData\Local\Microsoft\WindowsApps\python.exe
```
`python --version` 이 `Python ` 만 출력. **`uv run` 은 영향 없음** — 별개. 향후 PATH 정리 권장.

## 🎤 발표 메시지 확정 (5/23) — 선택지 3

> **"동일 chunker 로 비교하려 했으나, CPU 환경에서 SemanticChunker 가 비현실적임을 발견. 운영 비용의 trade-off 를 정량화함."**

### 검토한 세 선택지

| 옵션 | 비교 정직성 | 발표 시간 안전성 | 디버깅 가치 박제 | 회사 레포 건드림 |
|---|---|---|---|---|
| 1. 양쪽 동기화 | ◎ | △ | ◯ | ◎ |
| 2. 원본 그대로 | ◎ | △ (1시간+) | × | × |
| **3. 디버깅 = 메시지** ⭐ | △ (옵션 OFF 면 OK) | ◎ | ◎ | × |

선택지 3 채택 이유:
- **SEOCHO 멘토링 원칙 일치**: "GraphRAG는 도구 중 하나일 뿐, 만능이 아님 — 유용한 부분을 발견하는 것이 핵심" (Week 1 Session 2 Financial Expert)
- **엔지니어링 사고력 증거**: 단순 성능 비교 → trade-off 분석 → production 적용 가능성 판단
- **발표 시간 안전**: fallback 으로 8문서 적재 30분 → 발표 시드 확보

### 발표 구조 (6슬라이드 + 데이터 슬라이드)

1. **문제 정의**: 회사 레포 (VectorRAG, SemanticChunker) vs doc-graph-agent (GraphRAG) 동일 환경 비교 시도
2. **발견**: SemanticChunker + bge-m3 + CPU = 820자 / 31.3초 (단독 벤치 결과)
3. **분석**: LangChain SemanticChunker 가 임베딩을 sequential 호출 (batch 미사용)
4. **trade-off 표**: semantic 분할 품질 vs production 비용 (8문서 1시간+ vs 30분)
5. **결정 + fallback 구현**: USE_SIMPLE_CHUNKER 환경변수, chunk 정책은 동일 유지
6. **인사이트**: "RAG 비교 실험은 동일 chunker 가 전제. CPU 한계가 메타-비교 차원 변수"
7. **데이터**: 1문서 sanity 결과 + Aura 통계 (14 Company / 6 Risk / 4 Metric / 3 Outlook, MENTIONS 108)
8. **그래프 시각화**: Aura console 캡처 (Layer A + Layer B + MENTIONS)

### "그래서 결국 성능 비교는?" 질문 대응

답변 준비:
- "SemanticChunker 원본은 production 환경(GPU/API) 마련 후 별도 시도 예정"
- "fallback 으로도 **chunk 정책(size, overlap, min)** 은 동일하게 통제했고, **Layer 구조의 효과** 는 entity 그룹화율 / NED compression ratio / 그래프 시각화로 측정"
- "오히려 이 발견 자체가 production 환경에서 어떤 도구가 적용 가능한지의 실용적 정보"
- "실제 측정값: 1문서 DS투자증권 — 113 raw entity → 55 group (compression 0.49), MENTIONS 108 적재 완료"

## 8문서 일괄 적재 결과

### 5/16 1문서 sanity (DS투자증권만)

| 파일 | 포맷 | 타입 | sec | chunks(T/B) | ent(raw→grp) | rel | mentions | parse | extract | link | neo4j | total | ok |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| DS투자증권_시황분석_리포트.pdf | pdf | report | 6 | 52/0 | 113→55 | 28 | 108 | 8.6 | 146.3 | 33.6 | 39.0 | 227.5 | ✅ |

### 5/17 8문서 전체 (예정)

```
TODO: cmd 에서 uv run python -u -m scripts.run_w3_batch 실행 후 stdout 의 표 박제
```

## 시행착오 박제

5/16 토요일 디버깅 자산 (= 발표 슬라이드 시드):
- ✅ **bge-m3 정상** (5.4초/50문장 = 108ms/문장)
- ✅ **PDF / OCR / Neo4j / SemanticChunker 초기화 모두 정상**
- ❌ **SemanticChunker.split_text 본질적 비효율** — 820자/31초, CPU 환경 비현실적
- ✅ **해결책 확정**: 옵션 B (RecursiveCharacterTextSplitter fallback, commit `8f0bcb1`)
- ✅ **발표 메시지 확정**: 선택지 3 (디버깅 = trade-off 인사이트)
- ✅ **1문서 sanity 성공** + **Aura 통계 4종 확인**
- **Aura Free trial** — 새 인스턴스 `9b57188f` 로 우회
- **MS Store python stub** — `uv run` 영향 없음

남은 예상 시행착오 (5/17 검증):
- **HWP 파서** — 농협 사업보고서 (HWP 포맷). pyhwp / hwp5 등 라이브러리 의존성 이슈 가능
- **DOC 파서** — 금감원 보도자료 (.doc, .docx 아님). LibreOffice headless 필요 가능성
- **큰 PDF** — 미래에셋 4분기 실적보고서가 50+ 청크면 Kimi 비용 + 시간 부담

### local_id 충돌 — 옵션 3 으로 해결

청크 N 개에서 각각 `ent_001` 부터 부여 → 다중 청크 시 충돌.
해결: chunk dict 에 `chunk_id` 박아 보내면 extractor 가 자동 `{chunk_id}__` prefix.
파이프라인 흐름:

```
adapter.parse_document() → Document.sections[].chunks[].id ("doc1:c0001")
                              ↓ (run_w3_batch._doc_to_extract_chunks)
chunks = [{doc_id, chunk_id, section, text}]
                              ↓ extract() — chunk_id 보고 결과 prefix
ExtractedEntity.local_id = "doc1:c0001__ent_001"
                              ↓ link_entities() — 청크 간 NED 가능
EntityGroup.members[*].local_id = "doc1:c0001__ent_001"  (각자)
                              ↓ link_chunks_to_entities()
parse_global_id("doc1:c0001__ent_001") → ("doc1:c0001", "ent_001")
                              ↓
(:Chunk {id:"doc1:c0001"}) -[:MENTIONS]-> (:Entity {group_id:"grp_001"})
```

## 그래프 통계 (Aura console / Cypher)

### 5/16 1문서 sanity 후 측정값

위 "🏆 5/16 1문서 sanity 결과 — Aura console Cypher 통계" 섹션 참고.

### 5/17 8문서 적재 후 재측정 (예정)

```cypher
// 노드 라벨별
MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC;

// 관계 타입별
MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS n ORDER BY n DESC;

// Layer A → Layer B 연결 확인
MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
RETURN labels(e)[1] AS type, count(DISTINCT c) AS chunks, count(e) AS mentions
ORDER BY mentions DESC LIMIT 10;

// 미래에셋증권 NED 검증 — 4분기 문서 4개에서 같은 entity 그룹화 됐는지
MATCH (e:Entity:Company {name: "미래에셋증권"})<-[:MENTIONS]-(c:Chunk)<-[:CONTAINS_CHUNK]-(s:Section)<-[:HAS_SECTION]-(d:Document)
RETURN DISTINCT d.filename;
```

## 발표 자료 시드 (5/23 용)

| 자료 | 출처 |
|---|---|
| 1문서 → 8문서 적재 운영 데이터 표 | 본 문서 |
| **🎯 Aura 통계 (Entity 타입별 14/6/4/3)** | 본 문서 |
| **🎯 NED compression 0.49 정량화** | 본 문서 |
| Layer A + Layer B + MENTIONS 그래프 시각화 | Aura console 스크린샷 |
| 포맷 다양성 (PDF/DOC/HWP) → 통합 그래프 | 본 문서 + 그래프 캡처 |
| `@track` 으로 자동 수집된 trace | Opik UI |
| 미래에셋 4분기 NED 효과 — 청크 간 같은 entity 그룹화 | linking.compression_ratio |
| **🎯 SemanticChunker+bge-m3+CPU 본질적 비효율 (820자/31초)** | 본 문서 진단 표 |
| **🎯 trade-off 표: semantic 분할 vs 단순 분할** | 본 문서 |
| **🎯 USE_SIMPLE_CHUNKER fallback 코드 + 정직성 원칙** | commit `8f0bcb1` |

## 관련

- PR: #45 (8문서 sanity 완료 후 머지)
- 의존: ✅ PR #44 (#24 Opik 1단계)
- 후속: #18 Text2Cypher (Layer A 적재된 그래프 위에서)
