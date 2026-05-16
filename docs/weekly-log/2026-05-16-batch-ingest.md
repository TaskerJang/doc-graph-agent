# 2026-05-16 — W3 batch ingest (#17)

> Status: **5/16 코드 완성 + 단위 테스트 통과, 8문서 sanity 는 5/17(일) 풀데이로 이월**

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

- **단위 테스트 11/11 PASS** — `tests/kg/test_builder_layer_a.py`
  - build_layer_a (7): 노드 수치 / Document params / Section label 직렬화 / Section label None / NEXT 경계 / CONTAINS_TABLE / MERGE 기반 idempotent
  - link_chunks_to_entities (4): 기본 / dedupe / 다중 청크 / 구식 local_id graceful drop
- **옵션 3 prefix 로직 검증** — `make_global_id` / `parse_global_id` round-trip + chunk_id 내부 `_` 충돌 케이스 모두 통과
- **PR #45 생성** — https://github.com/TaskerJang/doc-graph-agent/pull/45
- **새 Aura Free 인스턴스 구축** — ID `9b57188f` (기존 trial expired 후 재생성)
- **`.env` 갱신 완료** — 새 NEO4J_URI / NEO4J_PASSWORD

## ⚠️ 5/16 토요일 미완료 — 8문서 실제 sanity 이월

### 발견 확정: **SemanticChunker hang** (Neo4j 와 무관)

5/16 두 번 시도, 두 번 모두 같은 자리에서 멈춤:

**1차 시도 (11:38, PyCharm 안 + 기존 Aura)**:
```
11:38:28  SemanticChunker 초기화 완료 (bge-m3, percentile=85.0)
[이후 5분+ 정적]
```
작업 관리자: Python 프로세스 2.12GB, CPU 42% — 진짜 일하는 중인데 끝없이 안 끝남.

**2차 시도 (12:10, cmd `-u` + 새 Aura `9b57188f`)**:
```
12:10:39  Neo4j connectivity OK (uri=neo4j+s://9b57188f.databases.neo4j.io)
12:10:57  SemanticChunker 초기화 완료 (bge-m3, percentile=85.0)
[이후 정적]
```

→ **Neo4j 문제 아님 확정** (새 인스턴스에서도 동일 현상).
→ **PyCharm 환경 문제 아님 확정** (cmd `-u` 에서도 동일 현상).
→ 진짜 원인: **`SemanticChunker.split_documents()` 의 bge-m3 임베딩이 CPU 환경에서 너무 느림**.

### 부가 발견: Aura Free trial 정책

기존 인스턴스가 "Trial expired" 상태로 전환 → console UI 에 Extend 버튼 클릭 시 **유료 Professional 신용카드 입력 강제**.
해결: 기존 인스턴스 폐기 + 새 Free 인스턴스 생성 (`9b57188f`). 신용카드 없이 정상 생성. 14일 후 또 만료될 가능성 있음 (또는 정책 변경).

### 별도 발견 — MS Store python stub 이 PATH 에 있음

```
C:\Users\taske\doc-graph-agent>where python
C:\Users\taske\AppData\Local\Microsoft\WindowsApps\python.exe
```

`python --version` 이 `Python ` 만 출력하고 끝나는 원인. **`uv run` 은 본인 가상환경 python 을 직접 호출하므로 영향 없음** — 별개 문제. 향후 PATH 정리 권장.

## 5/17(일) 풀데이 디버깅 계획

### 우선순위 #1 — SemanticChunker 의 bge-m3 임베딩 속도 문제 해결

다음 옵션 중 택일:

**A. langchain-huggingface 마이그레이션** (LangChain 권장)
```cmd
uv pip install -U langchain-huggingface
```
그리고 `ingestion/chunker.py` 의 `HuggingFaceBgeEmbeddings` import 를 `langchain_huggingface.HuggingFaceEmbeddings` 로 교체.
가능성: 새 패키지가 sentence-transformers 직접 호출이라 더 빠를 수 있음.

**B. SemanticChunker 끄고 단순 토큰 길이 기반 분할 fallback** (sanity 만 빠르게)
`ingestion/chunker.py` 에 환경 변수 `USE_SIMPLE_CHUNKER=1` 로 `RecursiveCharacterTextSplitter` 분기 추가.
sanity 빠르게 보고 → Layer A + 옵션 3 + MENTIONS 동작 검증 → 발표 자료 시드 확보.
sematic 분할은 발표 후 또는 GPU 환경 마련 후 다시.

**C. 더 작은 임베딩 모델로 교체** (예: `paraphrase-multilingual-MiniLM-L12-v2`)
bge-m3 (568M params) → MiniLM (118M) 으로 4-5배 빠름. 한국어 품질 약간 떨어지지만 sanity 용으로 충분.

**가장 빠른 길**: 옵션 B (단순 분할) — 5/23 발표 자료 시드 확보가 최우선, 정밀 분할은 W4 디버깅 작업으로 따로.

### 우선순위 #2 — 단독 검증으로 진짜 원인 좁히기

옵션 A/B/C 시도 전에 어디서 막히는지 정확히 짚고 가는 게 안전:

```cmd
# 1. bge-m3 임베딩 단독 — 30초 안에 끝나면 OK
uv run python -u -c "from langchain_community.embeddings import HuggingFaceBgeEmbeddings; e = HuggingFaceBgeEmbeddings(model_name='BAAI/bge-m3'); print(e.embed_query('한국어 테스트')[:5])"

# 2. SemanticChunker 단독 — 짧은 텍스트 1개
uv run python -u -c "from ingestion.chunker import SemanticChunker; c = SemanticChunker(); print(c.split_text('첫 문장입니다. 두 번째 문장입니다. 세 번째 문장입니다.'))"

# 3. PDF 1쪽 직접 parse_document 만 — Neo4j 등 모두 우회
uv run python -u -c "from ingestion.adapter import parse_document; from pathlib import Path; d = parse_document(Path('eval/dataset/documents/DS투자증권_시황분석_리포트.pdf')); print(f'sections={len(d.sections)}, chunks={sum(len(s.chunks) for s in d.sections)}')"
```

1번에서 막히면 → 환경 문제 (sentence-transformers / torch 설치 손상)
2번에서 막히면 → SemanticChunker 로직 자체 (이게 가장 의심)
3번에서 막히면 → adapter 의 다른 단계 (table-transformer? OCR? PDF 파싱?)

### 우선순위 #3 — 해결 후 sanity → 8문서 풀 실행

해결되면:
```cmd
uv run python -u -m scripts.run_w3_batch --limit 1
# 잘 되면
uv run python -u -m scripts.run_w3_batch
```

## 8문서 일괄 적재 결과

> 5/17 일요일에 채울 자리

```
TODO: cmd 에서 uv run python -u -m scripts.run_w3_batch 실행 후 stdout 의 표 박제
```

## 시행착오 박제

> 5/17 일요일 실행 시 발견되는 것 추가

예상되는 시행착오 후보 (미리 박제 + 본인이 검증):
- **SemanticChunker hang** — 5/16 발견 확정. 5/17 디버깅 우선순위 #1
- **Aura Free trial 만료** — 5/16 발견. 새 인스턴스 `9b57188f` 로 우회. 14일 후 또 갱신 필요할 가능성
- **HWP 파서** — 농협 사업보고서 (HWP 포맷). pyhwp / hwp5 등 라이브러리 의존성 이슈 가능
- **DOC 파서** — 금감원 보도자료 (.doc, .docx 아님). LibreOffice headless 필요 가능성
- **큰 PDF** — 미래에셋 4분기 실적보고서가 50+ 청크면 Kimi 비용 + 시간 부담
- **bge-m3 메모리** — 8문서 전체 entity 가 100+ 면 임베딩 비용 ↑

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
| **시행착오: SemanticChunker hang + 해결책 (선택한 옵션)** | 5/17 디버깅 결과 |

## 관련

- PR: #45 (sanity 완료 후 머지)
- 의존: ✅ PR #44 (#24 Opik 1단계)
- 후속: #18 Text2Cypher (Layer A 적재된 그래프 위에서)

## 5/17(일) 풀데이 계획

1. **bge-m3 / SemanticChunker 단독 검증** (위 단독 검증 명령 3개)
2. 막힘 단계 확인 후 옵션 A/B/C 중 선택
3. 권장: **옵션 B (단순 분할 fallback)** — 발표 시드 확보 최우선
4. `--limit 1` sanity → 성공 시 8문서 풀 실행
5. 결과 표 + 그래프 통계 + Opik trace 캡처 → 본 문서에 박제
6. PR #45 머지 + 이슈 #17 close
7. **#18 W4 Text2Cypher Agent** 진행 (Layer A 적재된 풍성한 그래프 위에서)
