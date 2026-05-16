# 2026-05-16 — W3 batch ingest (#17)

> Status: **코드 100% 완료 (chunker fix 포함), 8문서 sanity 만 5/17(일) 으로 이월.**
> 발표 메시지 확정: **선택지 3 — 디버깅 자체를 trade-off 인사이트로**

## 🎯 5/17(일) 즉시 시작 가이드 (최상단 — 컨텍스트 복구 0초)

### Step 1 — git pull + .env 갱신 (1분)

```cmd
cd C:\Users\taske\doc-graph-agent
git checkout feat/17-batch-ingest
git pull origin feat/17-batch-ingest
```

`.env` 에 한 줄 추가:
```
USE_SIMPLE_CHUNKER=1
```

### Step 2 — sanity (2-5분)

```cmd
uv run python -u -m scripts.run_w3_batch --limit 1
```

확인 포인트:
- 로그에 `USE_SIMPLE_CHUNKER=1 → SemanticChunker 우회, RecursiveCharacterTextSplitter 사용`
- Layer A 적재 완료, Layer B 적재 완료, MENTIONS 적재 완료
- Aura console 에서 노드 수 0 → N 변화

### Step 3 — 8문서 풀 실행 (10-20분)

```cmd
uv run python -u -m scripts.run_w3_batch
```

stdout 의 markdown 표 복붙 → 본 문서 "8문서 일괄 적재 결과" 섹션.

### Step 4 — 결과 박제 + PR 머지

- Aura Cypher 쿼리 4종 실행 → 본 문서 "그래프 통계"
- Opik UI 스크린샷 → 발표 자료 폴더
- PR #45 머지 + 이슈 #17 close

### Step 5 — #18 W4 Text2Cypher 시작

Layer A 적재된 풍성한 그래프 위에서.

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

### 환경
- **새 Aura Free 인스턴스 구축** — ID `9b57188f` (기존 trial expired 후 재생성)
- **`.env` 갱신 완료** — 새 NEO4J_URI / NEO4J_PASSWORD

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
- **발표 시간 안전**: fallback 으로 8문서 적재 10-20분 → 발표 시드 확보

### 발표 구조 (6슬라이드)

1. **문제 정의**: 회사 레포 (VectorRAG, SemanticChunker) vs doc-graph-agent (GraphRAG) 동일 환경 비교 시도
2. **발견**: SemanticChunker + bge-m3 + CPU = 820자 / 31.3초 (단독 벤치 결과)
3. **분석**: LangChain SemanticChunker 가 임베딩을 sequential 호출 (batch 미사용)
4. **trade-off 표**: semantic 분할 품질 vs production 비용 (8문서 1시간+ vs 20분)
5. **결정 + fallback 구현**: USE_SIMPLE_CHUNKER 환경변수, chunk 정책은 동일 유지
6. **인사이트**: "RAG 비교 실험은 동일 chunker 가 전제. CPU 한계가 메타-비교 차원 변수"

### "그래서 결국 성능 비교는?" 질문 대응

답변 준비:
- "SemanticChunker 원본은 production 환경(GPU/API) 마련 후 별도 시도 예정"
- "fallback 으로도 **chunk 정책(size, overlap, min)** 은 동일하게 통제했고, **Layer 구조의 효과** 는 entity 그룹화율 / NED compression ratio / 그래프 시각화로 측정"
- "오히려 이 발견 자체가 production 환경에서 어떤 도구가 적용 가능한지의 실용적 정보"

## 5/17(일) 풀데이 작업 계획

위 "🎯 5/17(일) 즉시 시작 가이드" 의 Step 1~5 그대로.

## 8문서 일괄 적재 결과

> 5/17 일요일에 채울 자리

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

5/17 8문서 적재 성공 후 다음 쿼리로 통계 확인 → 본 문서에 박제:

```cypher
// 노드 라벨별
MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC;

// 관계 타입별
MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS n ORDER BY n DESC;

// Layer A → Layer B 연결 확인
MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
RETURN e.entity_type AS type, count(DISTINCT c) AS chunks, count(e) AS entities
ORDER BY chunks DESC;

// 미래에셋증권 NED 검증 — 4분기 문서 4개에서 같은 entity 그룹화 됐는지
MATCH (e:Entity:Company {name: "미래에셋증권"})<-[:MENTIONS]-(c:Chunk)<-[*]-(d:Document)
RETURN DISTINCT d.filename;
```

## 발표 자료 시드 (5/23 용)

| 자료 | 출처 |
|---|---|
| 8문서 적재 운영 데이터 표 | 본 문서 |
| Layer A + Layer B 그래프 시각화 | Aura console 스크린샷 |
| 포맷 다양성 (PDF/DOC/HWP) → 통합 그래프 | 본 문서 + 그래프 캡처 |
| `@track` 으로 자동 수집된 8문서 trace | Opik UI |
| 미래에셋 4분기 NED 효과 — 청크 간 같은 entity 그룹화 | linking.compression_ratio |
| **🎯 SemanticChunker+bge-m3+CPU 본질적 비효율 (820자/31초)** | 본 문서 진단 표 |
| **🎯 trade-off 표: semantic 분할 vs 단순 분할** | 본 문서 |
| **🎯 USE_SIMPLE_CHUNKER fallback 코드 + 정직성 원칙** | commit `8f0bcb1` |

## 관련

- PR: #45 (sanity 완료 후 머지)
- 의존: ✅ PR #44 (#24 Opik 1단계)
- 후속: #18 Text2Cypher (Layer A 적재된 그래프 위에서)
