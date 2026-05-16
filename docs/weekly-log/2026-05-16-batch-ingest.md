# 2026-05-16 — W3 batch ingest (#17)

> Status: **DRAFT** — 본인 로컬 실제 실행 결과로 표 채우기

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

## 8문서 일괄 적재 결과

> 본인이 `uv run python -m scripts.run_w3_batch` 실행 후 stdout 의 표를 여기에 복사

```
TODO: 본인 로컬 실행 후 결과 표 박제
```

## 시행착오 박제

> 본인 로컬 실행 시 발견되는 것 추가

예상되는 시행착오 후보 (미리 박제 + 본인이 검증):
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

본인 로컬 8문서 적재 후 다음 쿼리로 통계 확인 → 본 문서에 박제:

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

- PR: #45 (예정)
- 의존: ✅ PR #44 (#24 Opik 1단계)
- 후속: #18 Text2Cypher (Layer A 적재된 그래프 위에서)
