# 2026-05-16 — W3 batch ingest (#17)

> Status: **5/16 코드 + 단위 테스트 + 진단 100% 완료. 옵션 B fix 한 줄 + 8문서 sanity 만 5/17(일) 으로 이월.**

## 🎯 5/17(일) 즉시 시작 가이드 (최상단 — 컨텍스트 복구 0초)

### 진짜 hang 원인 — 100% 확정

**LangChain `SemanticChunker` + bge-m3 + CPU = 본질적으로 너무 느림.**

벤치마크 (5/16 단독 측정):
| 입력 | 시간 |
|---|---|
| bge-m3 50문장 batch=32 | 5.4초 (OK) |
| **SemanticChunker `split_text(820자)`** | **31.3초 (비현실적)** |

추정:
- 4464자 DS투자증권 PDF 1쪽 → 약 3분
- 8문서 전체 → **40분~1시간** (적재 안 하고 분할만)

→ SemanticChunker 는 문장을 batch 안 쓰고 sequential 임베딩 호출. CPU 환경에서 못 씀. **OpenAI API embedding 같은 빠른 임베딩 짝궁용**.

### Fix — 옵션 B 한 줄 (5분 작업)

**Step 1**: `ingestion/chunker.py` 의 `_semantic_split()` 함수 맨 위에 추가

```python
import os
from langchain_text_splitters import RecursiveCharacterTextSplitter

def _semantic_split(text: str) -> list[str]:
    # 5/16 발견: SemanticChunker+bge-m3+CPU = 820자/31초 (비현실적, 발표 못 씀)
    # 옵션 B: 환경변수로 단순 분할 fallback. semantic 분할은 발표 후 GPU/API 마련 후
    if os.getenv("USE_SIMPLE_CHUNKER") == "1":
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=DEFAULT_CHUNK_SIZE,
            chunk_overlap=DEFAULT_CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", "。", "? ", "! ", " ", ""],
        )
        return splitter.split_text(text)

    # ── 기존 코드 (변경 없음) ──
    sentences = [s for s in re.split(KOREAN_SENTENCE_SPLIT_REGEX, text) if s.strip()]
    # ...
```

**Step 2**: `.env` 에 추가
```
USE_SIMPLE_CHUNKER=1
```

**Step 3**: sanity
```cmd
cd C:\Users\taske\doc-graph-agent
uv run python -u -m scripts.run_w3_batch --limit 1
```

→ **30초~2분 안에 끝남** (Kimi 추출 시간이 대부분). 분할은 즉시.

**Step 4**: 잘 되면 8문서 풀 실행
```cmd
uv run python -u -m scripts.run_w3_batch
```

→ **10~20분 예상** (8문서 × Kimi 호출 + bge-m3 NED + Neo4j 적재).

### 검증 후 PR #45 머지 + 이슈 #17 close + **#18 W4 Text2Cypher**

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

## ✅ 5/16 토요일 검증 완료 사항

### 코드/테스트
- **단위 테스트 11/11 PASS** — `tests/kg/test_builder_layer_a.py`
  - build_layer_a (7): 노드 수치 / Document params / Section label 직렬화 / Section label None / NEXT 경계 / CONTAINS_TABLE / MERGE 기반 idempotent
  - link_chunks_to_entities (4): 기본 / dedupe / 다중 청크 / 구식 local_id graceful drop
- **옵션 3 prefix 로직 검증** — `make_global_id` / `parse_global_id` round-trip + chunk_id 내부 `_` 충돌 케이스 모두 통과
- **PR #45 생성** — https://github.com/TaskerJang/doc-graph-agent/pull/45

### 환경
- **새 Aura Free 인스턴스 구축** — ID `9b57188f` (기존 trial expired 후 재생성)
- **`.env` 갱신 완료** — 새 NEO4J_URI / NEO4J_PASSWORD

### 진단 (1.5시간 디버깅 결과 — 자산)

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

**chunker.py `encode_kwargs` 부족** (참고)
```python
# 현재
encode_kwargs={"normalize_embeddings": True},
# 권장 (다음 PR 에서)
encode_kwargs={"normalize_embeddings": True, "batch_size": 32, "show_progress_bar": True},
```
다만 이건 chunker 의 본질적 hang 과는 별개 — SemanticChunker 가 어차피 sequential 호출이라 batch_size 효과 미미.

## 5/17(일) 풀데이 디버깅 계획 (위 최상단 가이드 + 상세)

### Step 0 — 컨텍스트 복구 (1분)

본 문서 최상단 "🎯 5/17(일) 즉시 시작 가이드" 섹션 읽기.

### Step 1 — chunker.py 옵션 B fix (5분)

`ingestion/chunker.py` 의 `_semantic_split()` 함수에 환경변수 분기 추가:

```python
def _semantic_split(text: str) -> list[str]:
    if os.getenv("USE_SIMPLE_CHUNKER") == "1":
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=DEFAULT_CHUNK_SIZE,
            chunk_overlap=DEFAULT_CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", "。", "? ", "! ", " ", ""],
        )
        return splitter.split_text(text)
    # ... (기존 코드)
```

`.env` 에 `USE_SIMPLE_CHUNKER=1` 추가.

### Step 2 — sanity (2-5분)

```cmd
uv run python -u -m scripts.run_w3_batch --limit 1
```

### Step 3 — 8문서 풀 실행 (10-20분)

```cmd
uv run python -u -m scripts.run_w3_batch
```

### Step 4 — 결과 박제

- stdout 의 markdown 표 → 본 문서 "8문서 일괄 적재 결과" 섹션
- Aura console 에서 Cypher 통계 → 본 문서 "그래프 통계" 섹션
- Opik UI 의 trace 스크린샷 → 발표 자료
- 시행착오 (HWP/DOC/큰 PDF 발견되는 것) → 본 문서 "시행착오 박제" 섹션

### Step 5 — PR #45 머지 + 이슈 #17 close

GitHub 웹에서 PR #45 Merge → 이슈 #17 close.

### Step 6 — #18 W4 Text2Cypher 시작

Layer A 적재된 풍성한 그래프 위에서.

## 8문서 일괄 적재 결과

> 5/17 일요일에 채울 자리

```
TODO: cmd 에서 uv run python -u -m scripts.run_w3_batch 실행 후 stdout 의 표 박제
```

## 시행착오 박제

5/16 토요일 디버깅 자산 (=발표 슬라이드 시드):
- ✅ **bge-m3 정상** (5.4초/50문장 = 108ms/문장)
- ✅ **PDF / OCR / Neo4j / SemanticChunker 초기화 모두 정상**
- ❌ **SemanticChunker.split_text 본질적 비효율** — 820자/31초, CPU 환경 비현실적
- ✅ **해결책 확정**: 옵션 B (RecursiveCharacterTextSplitter fallback)
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
| **시행착오: SemanticChunker+bge-m3+CPU 본질적 비효율 (820자/31초)** | 본 문서 |
| **trade-off: semantic 분할 vs 단순 분할 — 발표용은 후자 우선** | 본 문서 |

## 관련

- PR: #45 (sanity 완료 후 머지)
- 의존: ✅ PR #44 (#24 Opik 1단계)
- 후속: #18 Text2Cypher (Layer A 적재된 그래프 위에서)
