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

## ⚠️ 5/16 토요일 미완료 — 8문서 실제 sanity 이월

### 발견된 문제: SemanticChunker 단계 hang

`uv run python -m scripts.run_w3_batch --limit 1` (DS투자증권 시황분석 1쪽 PDF) 시도 시 SemanticChunker 초기화 직후에서 5분+ 멈춤. 로그 마지막 라인:

```
2026-05-16 11:38:28,852 [INFO] ingestion.chunker: SemanticChunker 초기화 완료 (bge-m3, percentile=85.0)
[이후 로그 없음 — 5분+ 정적]
```

작업 관리자 확인: python 프로세스 1.25GB 메모리 점유, **CPU 0.1%** — 진행 중이 아니라 사실상 멈춤.

### 의심 후보 (5/17 디버깅 대상)

1. **SemanticChunker.split_documents 의 bge-m3 첫 임베딩 호출 hang**
   - LangChain `HuggingFaceBgeEmbeddings` (deprecated 경고 떴음) + 최신 sentence-transformers + CPU 환경
   - 첫 `encode()` 가 warm-up 으로 진짜 오래 걸리거나 thread pool 데드락
2. **PyCharm Run/Debug 환경 영향**
   - 본 시도는 PyCharm 안에서 돌렸음. 디버거 hook 이 끼었을 가능성
   - cmd 에서 `-u` 플래그로 다시 시도해야 깨끗한 환경 확인

### 5/17(일) 디버깅 순서

```cmd
# 1. cmd 에서 unbuffered 로 다시
cd C:\Users\taske\doc-graph-agent
uv run python -u -m scripts.run_w3_batch --limit 1

# 2. 같은 자리에서 hang 되면 SemanticChunker 단독 검증
uv run python -c "from ingestion.chunker import SemanticChunker; c = SemanticChunker(); print(c.split_text('테스트 문장. 두 번째 문장.'))"

# 3. bge-m3 임베딩 단독 검증
uv run python -c "from langchain_community.embeddings import HuggingFaceBgeEmbeddings; e = HuggingFaceBgeEmbeddings(model_name='BAAI/bge-m3'); print(e.embed_query('test')[:5])"
```

### 별도 발견 — MS Store python stub 이 PATH 에 있음

```
C:\Users\taske\doc-graph-agent>where python
C:\Users\taske\AppData\Local\Microsoft\WindowsApps\python.exe
```

이게 진짜 Python 아니라 MS Store launcher stub. `python --version` 명령이 `Python ` 만 출력하고 끝나는 원인. **`uv run` 은 본인 가상환경 python 을 직접 호출하므로 영향 없음** — sanity hang 과 별개 문제. 다만 향후 `python` 단독 호출 시 혼란 방지 위해 PATH 정리 권장.

## 8문서 일괄 적재 결과

> 5/17 일요일에 채울 자리

```
TODO: cmd 에서 uv run python -u -m scripts.run_w3_batch 실행 후 stdout 의 표 박제
```

## 시행착오 박제

> 5/17 일요일 실행 시 발견되는 것 추가

예상되는 시행착오 후보 (미리 박제 + 본인이 검증):
- **SemanticChunker hang** — 5/16 발견. 5/17 디버깅 우선순위 #1
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

## 관련

- PR: #45 (sanity 완료 후 머지)
- 의존: ✅ PR #44 (#24 Opik 1단계)
- 후속: #18 Text2Cypher (Layer A 적재된 그래프 위에서)

## 5/17(일) 풀데이 계획

1. **SemanticChunker hang 디버깅** (위 명령어 순서대로)
2. 해결되면 `--limit 1` sanity → 성공 시 8문서 풀 실행
3. 결과 표 + 그래프 통계 + Opik trace 캡처 → 본 문서에 박제
4. PR #45 머지 + 이슈 #17 close
5. **#18 W4 Text2Cypher Agent** 진행 (Layer A 적재된 풍성한 그래프 위에서)
