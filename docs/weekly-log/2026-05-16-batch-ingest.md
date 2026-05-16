# 2026-05-16 — W3 batch ingest (#17)

> Status: **🎉🎉🎉 8문서 풀 적재 완료 (8/8 = 100% 성공)! DOC 도 LibreOffice 변환 후 적재 성공.**
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

```
1차 결과: 총 8문서 · 성공 7 · 실패 1 (DOC)
전체 소요: 4249.1s (≈ 71분)
```

### 2차 적재: DOC → DOCX 변환 후 (17:28~17:33, 5분) — 1/1 성공 ⭐

LibreOffice headless 로 `.doc` → `.docx` 수동 변환 후 재실행:

| 파일 | 포맷 | 타입 | sec | chunks(T/B) | ent(raw→grp) | rel | mentions | parse | extract | link | neo4j | total | ok |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 금융감독원_..._직접금융_조달실적.docx | **docx** | **disclosure** | 1 | **49/0** | **275→251** | 26 | **260** | 1.7 | 106.0 | 116.6 | 73.3 | 297.7 | ✅ |

```
2차 결과: 총 1문서 · 성공 1 · 실패 0
전체 소요: 297.7s (≈ 5분)
```

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
| **포맷 다양성** | PDF + HWP | DOC (변환) | **PDF + HWP + DOCX** ✅ |
| **doc_type 분류** | report / ir / filing | **disclosure** | **4가지 자동 분류** |

### 🌟 발표 자료 보석 (5/23 슬라이드 시드)

#### 1. ⭐⭐⭐ DOC 변환 + 재적재 성공 (NEW!)

5/16 토요일 1차 실행에서 ❌ 였던 금감원 보도자료를 **LibreOffice headless 변환 + 2차 재실행** 으로 ✅ 적재 완료.

- **49 청크 + 275 → 251 entity** (compression 0.91)
- **260 MENTIONS** + 26 relation
- **doc_type 자동 분류**: `disclosure` (보도자료)
- 변환 명령: `soffice.exe --headless --convert-to docx <파일>`

**발표 슬라이드**:
> **"production 환경 의존성 trade-off 의 실제 해소 사례 — LibreOffice headless 변환으로 .doc → .docx → 자동 적재. 1차 실패한 금감원 보도자료가 결국 49청크 + 251 entity + 260 MENTIONS 로 그래프에 통합."**

**엔지니어링 사이클 완성**:
```
1차 시도 (LibreOffice 미설치)  →  ❌ 실패
       ↓
원인 분석 (코드 보고 의존성 발견)
       ↓
2차 시도 (수동 변환 + 재적재)   →  ✅ 성공
       ↓
production 배포 가이드 박제 (Docker 이미지에 libreoffice 추가)
```

#### 2. HWP 파서 성공 ⭐
- 농협 사업보고서 (HWP 포맷) — **11 청크 + 56 entity + 56 MENTIONS 적재**
- pyhwp / hwp5 라이브러리 의존성 우려 → 실제로는 정상 동작 확인
- 다국적 포맷 (PDF + HWP + DOCX) 모두 통합 그래프 가능 검증

#### 3. 미래에셋 4분기가 진짜 풍부 ⭐
- 68 청크 + **6 표** (Table 노드 첫 적재!)
- **335 raw → 261 group** (compression 0.78)
- 329 MENTIONS — Layer A ↔ Layer B 연결 최대
- 발표 슬라이드: "큰 PDF + Table 통합 그래프"

#### 4. 미래에셋 3Q/4Q parse 시간 폭증
- 3Q: 1514.8초, 4Q: 1694.7초 — 다른 문서 대비 **100배+**
- 원인 추정: EasyOCR 캐시 없는 신규 PDF + 큰 파일 크기
- **발표 슬라이드**: "운영 환경의 OCR 비용 trade-off"

#### 5. NED compression 변동성
- DS투자증권 첫 sanity (5/16 13:00): 113→55 (0.49)
- DS투자증권 풀 실행 (5/16 16:05): 103→60 (0.58)
- 차이 원인: Kimi 의 비결정성 (temperature) — entity 추출 결과 매 호출 다름
- **발표 슬라이드**: "LLM 비결정성과 GraphRAG 의 robustness"

#### 6. doc_type 자동 분류 ⭐
8문서에서 4가지 doc_type 이 자동 분류됨:
- `report` (시황/기업분석)
- `ir` (실적보고서)
- `filing` (사업보고서)
- `disclosure` (보도자료) ← DOCX 변환 후 새로 확인!

→ **발표 슬라이드**: "포맷 다양성 + 도메인 다양성 — GraphRAG 가 한 그래프에 통합"

## 🏆 5/16 1문서 sanity 결과 (12:48~12:49) — 검증 자산

### 적재 운영 데이터

| 파일 | 포맷 | 타입 | sec | chunks(T/B) | ent(raw→grp) | rel | mentions | parse | extract | link | neo4j | total | ok |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| DS투자증권_시황분석_리포트.pdf | pdf | report | 6 | **52/0** | **113→55** | 28 | **108** | 8.6 | 146.3 | 33.6 | 39.0 | 227.5 | ✅ |

**1문서 → 약 4분**.

### Aura console Cypher 통계 (12:55 1문서 sanity 후 측정)

**Q1: 노드 라벨별** (총 114 노드)
```
| label    | n  |
|----------|----|
| Entity   | 55 |
| Chunk    | 52 |
| Section  | 6  |
| Document | 1  |
```

**Q2: 관계 타입별** (총 232 관계)
```
| rel             | n   |
|-----------------|-----|
| MENTIONS        | 108 | ← Layer A ↔ Layer B
| CONTAINS_CHUNK  | 52  |
| NEXT            | 46  |
| HAS_METRIC      | 13  |
| FACES_RISK      | 7   |
| HAS_SECTION     | 6   |
```

**Q3: Entity 타입별 분포** ⭐
```
| Type     | DISTINCT chunks | mentions |
|----------|-----------------|----------|
| Company  | 14              | 68       |
| Risk     | 6               | 21       |
| Metric   | 4               | 14       |
| Outlook  | 3               | 5        |
```
→ **Company 14 entity 평균 4.86 청크 언급** — NED 효과 정량화

### 🎤 1문서 발표 슬라이드 인사이트

> **"DS투자증권 1쪽 시황분석 리포트 → 14개 회사 + 6개 리스크 + 4개 지표 + 3개 전망. NED compression 0.49 로 entity 중복 51% 제거. Company 1개당 평균 4.86개 청크에서 언급 — VectorRAG 의 단순 유사도 검색으로는 못 얻는 다중 청크 entity 그래프 구조 확인."**

## ✅ 5/16 토요일 검증 완료 사항

### 코드/테스트
- **단위 테스트 11/11 PASS** — `tests/kg/test_builder_layer_a.py`
- **옵션 3 prefix 로직 검증** — round-trip + chunk_id 내부 `_` 충돌 케이스 통과
- **PR #45 생성** — https://github.com/TaskerJang/doc-graph-agent/pull/45
- **chunker.py fallback 추가** — commit `8f0bcb1`
- **🎉 1문서 sanity 성공** — DS투자증권 PDF, 227.5초
- **🎉 Aura Cypher 통계 4종 확인 완료** — 1문서 후 박제
- **🎉🎉🎉 8/8 적재 완료 (1차 7/8 + 2차 1/1 = 100%)** — 76분, 모든 포맷 통합

### 환경
- **새 Aura Free 인스턴스 구축** — ID `9b57188f` (기존 trial expired 후 재생성)
- **`.env` 갱신 완료** — 새 NEO4J_URI / NEO4J_PASSWORD / USE_SIMPLE_CHUNKER=1
- **LibreOffice 변환 확인** — 코드는 자동 변환 로직 있으나 본인 환경에 LibreOffice 미설치 → 수동 변환으로 검증

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

**LibreOffice 미설치 (Windows)**
- `ingestion/doc_parser/docx.py` 의 `_convert_doc_to_docx()` 가 `C:\Program Files\LibreOffice\program\soffice.exe` 호출
- 미설치 시 `FileNotFoundError` → `FileCorruptedError` → run_w3_batch graceful ❌
- 해결: LibreOffice 설치 또는 수동 변환 (본 케이스에서 사용)
- **production 배포 가이드**: Docker 이미지에 `apt-get install libreoffice-core` 추가 필요

## 🎯 5/17(일) 시작 가이드 (3단계로 마무리)

### Step 1 — Aura Cypher 통계 4종 재측정 (5분)

8/8 적재 후 그래프 통계 확인:

```cypher
// 1. 노드 라벨별
MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC;

// 2. 관계 타입별
MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS n ORDER BY n DESC;

// 3. Entity 타입별 분포 — 발표 핵심!
MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
RETURN labels(e)[1] AS type, count(DISTINCT c) AS chunks, count(e) AS mentions
ORDER BY mentions DESC LIMIT 10;

// 4. 미래에셋증권 NED 발표 보석! — 4개 분기 보고서 다 나와야 함
MATCH (e:Entity:Company {name: "미래에셋증권"})<-[:MENTIONS]-(c:Chunk)<-[:CONTAINS_CHUNK]-(s:Section)<-[:HAS_SECTION]-(d:Document)
RETURN DISTINCT d.filename;

// 5. ⭐ 8문서 doc_type 분포 — 포맷 + 도메인 다양성 증명
MATCH (d:Document)
RETURN d.source_format AS format, d.doc_type AS doc_type, count(*) AS n
ORDER BY n DESC;
```

결과 5개 캡처 → 본 문서 "그래프 통계 — 8문서" 섹션 박제.

### Step 2 — PR #45 머지 + 이슈 #17 close (1분)

https://github.com/TaskerJang/doc-graph-agent/pull/45 → **Merge pull request** 버튼.

머지 후:
```cmd
cd C:\Users\taske\doc-graph-agent
git checkout dev
git pull origin dev
git branch -d feat/17-batch-ingest
```

### Step 3 — #18 W4 Text2Cypher 시작 (다음 작업)

Layer A + Layer B + MENTIONS 적재된 풍성한 그래프 (277 청크 + 1,042 entity + 1,189 MENTIONS) 위에서.

```cmd
git checkout -b feat/18-text2cypher
```

이슈 #18 페이지 확인 → 작업 범위 파악 → ADR 또는 weekly-log 작성하며 시작.

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
- **발표 시간 안전**: fallback 으로 8문서 적재 76분 → 발표 시드 확보

### 발표 구조 (11슬라이드 — 데이터 강화)

1. **문제 정의**: 회사 레포 (VectorRAG, SemanticChunker) vs doc-graph-agent (GraphRAG) 동일 환경 비교 시도
2. **발견**: SemanticChunker + bge-m3 + CPU = 820자 / 31.3초 (단독 벤치 결과)
3. **분석**: LangChain SemanticChunker 가 임베딩을 sequential 호출 (batch 미사용)
4. **trade-off 표**: semantic 분할 품질 vs production 비용
5. **결정 + fallback 구현**: USE_SIMPLE_CHUNKER 환경변수, chunk 정책은 동일 유지
6. **운영 데이터 표 (8/8 100% 적재)**: 76분, 1,042 entity, 1,189 MENTIONS
7. **포맷 다양성**: PDF + HWP + **DOCX (LibreOffice 변환)** 통합 그래프
8. **production 배포 의존성**: LibreOffice 환경 의존성 발견 + 해소 사이클 ⭐ NEW!
9. **미래에셋 4분기 깊이**: 68 청크 + 6 표 + 335→261 entity (compression 0.78)
10. **NED + LLM 비결정성**: 같은 문서 2회 추출 → 113→55 vs 103→60 차이
11. **인사이트**: "RAG 비교 실험은 동일 chunker 가 전제. CPU 한계가 메타-비교 차원 변수"

### "그래서 결국 성능 비교는?" 질문 대응

답변 준비:
- "SemanticChunker 원본은 production 환경(GPU/API) 마련 후 별도 시도 예정 (Issue #46)"
- "fallback 으로도 **chunk 정책(size, overlap, min)** 은 동일하게 통제했고, **Layer 구조의 효과** 는 entity 그룹화율 / NED compression ratio / 그래프 시각화로 측정"
- "8/8 적재 실측: 1,212 raw → 1,042 group (compression 0.86), 1,189 MENTIONS, 255 relation"
- "4가지 doc_type 자동 분류 (report / ir / filing / disclosure)"
- "오히려 이 발견 자체가 production 환경에서 어떤 도구가 적용 가능한지의 실용적 정보"

## 시행착오 박제

5/16 토요일 디버깅 자산 (= 발표 슬라이드 시드):
- ✅ **bge-m3 정상** (5.4초/50문장 = 108ms/문장)
- ✅ **PDF / OCR / Neo4j / SemanticChunker 초기화 모두 정상**
- ❌ **SemanticChunker.split_text 본질적 비효율** — 820자/31초, CPU 환경 비현실적
- ✅ **해결책 확정**: 옵션 B (RecursiveCharacterTextSplitter fallback, commit `8f0bcb1`)
- ✅ **발표 메시지 확정**: 선택지 3 (디버깅 = trade-off 인사이트)
- ✅ **1문서 sanity 성공** + **Aura 통계 4종 확인**
- ✅ **8문서 1차 적재 성공** (7/8, 71분)
- ✅ **DOC → DOCX 변환 후 2차 적재 성공** (1/1, 5분) — **8/8 = 100% 달성** 🎉
- ✅ **HWP 파서 정상 동작** — 농협 사업보고서 적재 OK
- ✅ **Table 노드 첫 적재** — 미래에셋 4Q (6 표)
- ✅ **doc_type 4가지 자동 분류** — report / ir / filing / disclosure
- **Aura Free trial** — 새 인스턴스 `9b57188f` 로 우회
- **LibreOffice 환경 의존성** — Windows 미설치 시 .doc 변환 실패. production Docker 이미지에 추가 필요
- **MS Store python stub** — `uv run` 영향 없음

### 미래 발견 (#46+)

- **LibreOffice 자동화** — production 배포 시 Docker 이미지에 추가 또는 별도 변환 마이크로서비스
- **OCR 시간 폭증** — 3Q/4Q parse 1500초+ → OCR 캐시 또는 OCR 라이브러리 교체 검토
- **OpenAI 마이그레이션** (#46) — SemanticChunker 원본 동작 회복 + production 비교

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

### 5/16 1문서 sanity 후 측정값 (위 박제)

### 5/17 8문서 적재 후 재측정 (예정)

```
TODO: Aura console 에서 위 Step 1 의 5종 쿼리 실행 후 결과 박제
- Q1 노드 라벨별
- Q2 관계 타입별
- Q3 Entity 타입별 분포
- Q4 미래에셋증권 NED 4분기 검증 ⭐ — 발표 보석!
- Q5 doc_type 분포 — 포맷 + 도메인 다양성 증명
```

## 발표 자료 시드 (5/23 용)

| 자료 | 상태 | 출처 |
|---|---|---|
| 1문서 → 8/8 적재 운영 데이터 표 | ✅ 완료 | 본 문서 |
| **🎯 Aura 통계 (1문서: Entity 타입별 14/6/4/3)** | ✅ 완료 | 본 문서 Q3 |
| **🎯 8문서 Aura 통계 재측정** | ⏸️ 일요일 | TODO |
| **🎯 NED compression 0.49 → 0.86 (1→8문서)** | ✅ 완료 | 본 문서 |
| Layer A + Layer B + MENTIONS 그래프 시각화 | ⏸️ Aura console 캡처 | 일요일 |
| **🎯 포맷 다양성 (PDF + HWP + DOCX 통합)** ⭐ NEW! | ✅ 완료 | 본 문서 |
| **🎯 doc_type 자동 분류 4가지 (report/ir/filing/disclosure)** ⭐ NEW! | ✅ 완료 | 본 문서 |
| **🎯 LibreOffice 의존성 발견 + 해소 사이클** ⭐ NEW! | ✅ 완료 | 본 문서 |
| `@track` 으로 자동 수집된 trace | ✅ Opik UI 확인 가능 | Opik UI |
| **🎯 미래에셋 4분기 — 68 청크 + 6 표 + 261 entity** | ✅ 완료 | 본 문서 |
| **🎯 LLM 비결정성 — DS투자증권 2회 추출 차이** | ✅ 완료 | 본 문서 |
| **🎯 SemanticChunker+bge-m3+CPU 본질적 비효율 (820자/31초)** | ✅ 완료 | 본 문서 진단 표 |
| **🎯 trade-off 표: semantic 분할 vs 단순 분할** | ✅ 완료 | 본 문서 |
| **🎯 USE_SIMPLE_CHUNKER fallback 코드 + 정직성 원칙** | ✅ 완료 | commit `8f0bcb1` |

## 관련

- PR: #45 (5/17 일요일 머지 예정)
- 의존: ✅ PR #44 (#24 Opik 1단계)
- 후속: #18 Text2Cypher (Layer A 적재된 풍성한 그래프 위에서)
- 미래: #46 OpenAI 마이그레이션, #47 회사 발표 (6/1)
