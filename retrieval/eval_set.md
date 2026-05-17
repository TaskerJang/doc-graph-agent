# 2026-05-17 — W4 Text2Cypher 평가 셋 사이퍼 쿼리 (#18)

> **목적**: Text2Cypher 모듈 (`retrieval/text2cypher.py`) 의 정성 검증용 평가 셋. LLM 이 생성한 Cypher 와 비교할 정답 Cypher 들.
>
> **그래프 환경**: 5/16 적재 완료 (8문서 / 277 청크 / 261 entity / 1,189 MENTIONS, Aura `9b57188f`)
>
> **레퍼런스**: doc-summary-agent 의 LLM 프롬프트 패턴 + doc-ontology.md §3-§4 스키마

## 그래프 스키마 요약 (LLM 프롬프트 주입용)

### 노드 (610 총)

```
(:Document {filename, doc_type, source_format, ...})
(:Section  {id, label, heading_level, page_start, ...})
(:Chunk    {id, text, char_count, page, order_index, chunk_type, ...})
(:Table    {id, raw_markdown, row_count, column_count, ...})
(:Entity:Company        {group_id, name, aliases, member_count, ...})
(:Entity:Risk           {...})
(:Entity:Metric         {...})
(:Entity:Outlook        {...})
(:Entity:Recommendation {...})
```

### 관계 (2,451 총)

```
Layer A (문서 구조):
  (Document) -[:HAS_SECTION]->    (Section)
  (Section)  -[:CONTAINS_CHUNK]-> (Chunk)
  (Section)  -[:CONTAINS_TABLE]-> (Table)
  (Chunk)    -[:NEXT]->           (Chunk)

Layer B (Entity 의미):
  (Company)  -[:FACES_RISK]->       (Risk)
  (Company)  -[:HAS_METRIC]->       (Metric)
  (Company)  -[:HAS_OUTLOOK]->      (Outlook)
  (Company)  -[:RECOMMENDED_FOR]->  (Recommendation)

다리:
  (Chunk)    -[:MENTIONS]->         (Entity)
```

### doc_type 분포 (8문서)

| format | doc_type   | n | 예시 |
|--------|------------|---|------|
| pdf    | ir         | 4 | 미래에셋증권_1Q~4Q_실적보고서.pdf |
| pdf    | report     | 2 | DS투자증권_시황분석, 한화_두산밥캣 |
| hwp    | filing     | 1 | 농협_사업보고서.hwp |
| docx   | disclosure | 1 | 금융감독원_보도자료.docx |

---

## 평가 셋 질문 5종

### Q1. "DS투자증권 시황분석 리포트에서 언급된 entity 들은? (회사+metric 혼재 검증)"

**의도**: Layer A → MENTIONS → Layer B 기본 path traversal. 5/16 발견된 **Entity 라벨 품질 challenge** 정성 검증.

```cypher
MATCH (d:Document {filename: "DS투자증권_시황분석_리포트.pdf"})
      -[:HAS_SECTION]->(:Section)
      -[:CONTAINS_CHUNK]->(c:Chunk)
      -[:MENTIONS]->(e:Entity)
RETURN labels(e)[1] AS type, e.name, count(c) AS chunk_count
ORDER BY chunk_count DESC
LIMIT 100;
```

**예상 결과** (5/16 1차 적재 기준):
- 약 14개 Company entity (실제로는 회사명 + metric 혼재)
- 6개 Risk, 4개 Metric, 3개 Outlook
- Company 라벨 entity 중 "두산밥캣", "한국예탁결제원" 같은 진짜 회사명도 일부 있을 수 있음

**LLM 답변 가이드**:
> "DS투자증권 시황분석 리포트에서 N개의 entity 가 추출됐습니다. Company 라벨 X개, Risk Y개, Metric Z개, Outlook W개. 다만 일부 'Company' entity 는 실제 회사명이 아닌 금융 metric 으로 추출됐습니다 (라벨 품질 challenge)."

---

### Q2. "미래에셋증권 4분기 보고서의 Table 은 몇 개인가?"

**의도**: factual / numerical 질문. Layer A 의 Table 노드 카운트.

```cypher
MATCH (d:Document {filename: "미래에셋증권_4분기_실적보고서.pdf"})
      -[:HAS_SECTION]->(:Section)
      -[:CONTAINS_TABLE]->(t:Table)
RETURN count(t) AS table_count;
```

**예상 결과**: `6` (5/16 적재 데이터 그대로)

**LLM 답변 가이드**:
> "미래에셋증권 4분기 실적보고서에는 총 6개의 표(Table) 가 있습니다."

---

### Q3. "보도자료(disclosure) 유형 문서의 entity 들은?"

**의도**: doc_type 필터링 + Layer A → Layer B traversal. 4개 doc_type 다양성 활용.

```cypher
MATCH (d:Document {doc_type: "disclosure"})
      -[:HAS_SECTION]->(:Section)
      -[:CONTAINS_CHUNK]->(c:Chunk)
      -[:MENTIONS]->(e:Entity)
RETURN d.filename AS doc, labels(e)[1] AS type, e.name, count(c) AS mentions
ORDER BY mentions DESC
LIMIT 50;
```

**예상 결과**:
- 1개 문서: 금융감독원_보도자료.docx
- 49 청크에서 251개 entity 언급 (Q1 과 같은 라벨 혼재 패턴)

**LLM 답변 가이드**:
> "disclosure 유형 문서는 1건 (금융감독원 보도자료) 입니다. 49개 청크에서 251개 entity 가 그룹화되어 적재됐습니다. 주요 entity: ..."

---

### Q4. "두산밥캣과 함께 언급된 리스크가 있는가?"

**의도**: Layer B 의 의미 관계 활용. Company → FACES_RISK → Risk 직접 쿼리.

```cypher
// 정답 1: 직접 관계 검색
MATCH (c:Entity:Company)-[:FACES_RISK]->(r:Entity:Risk)
WHERE c.name CONTAINS "두산밥캣"
   OR ANY(alias IN c.aliases WHERE alias CONTAINS "두산밥캣")
RETURN c.name AS company, r.name AS risk;

// 정답 2: 같은 청크에 동시 언급 (대체 정답 — 직접 관계 없을 때)
MATCH (c1:Entity:Company)<-[:MENTIONS]-(chunk:Chunk)-[:MENTIONS]->(r:Entity:Risk)
WHERE c1.name CONTAINS "두산밥캣"
   OR ANY(alias IN c1.aliases WHERE alias CONTAINS "두산밥캣")
RETURN c1.name AS company, r.name AS risk, count(chunk) AS co_mention_count
ORDER BY co_mention_count DESC;
```

**예상 결과**:
- 한화투자증권_두산밥캣 분석 리포트에서 추출된 두산밥캣 entity 가 FACES_RISK 관계로 risk 와 연결됐는지 확인
- 직접 관계 없으면 co-mention 패턴으로 대체

**LLM 답변 가이드**:
> "두산밥캣과 연관된 리스크 N개가 발견됐습니다: [risk1, risk2, ...]. (FACES_RISK 직접 관계 / 청크 동시 언급)"

**graceful fallback**: 두산밥캣 entity 자체가 없으면 → "두산밥캣 관련 entity 를 그래프에서 찾지 못했습니다."

---

### Q5. "전체 그래프에서 가장 많이 언급된 Company 라벨 entity 5개는?"

**의도**: 5/16 발견된 **Entity 라벨 품질 challenge** 정량 검증. Top-N + member_count 활용.

```cypher
// 정답: 가장 많이 언급된 Company 라벨 entity
MATCH (e:Entity:Company)<-[:MENTIONS]-(c:Chunk)
RETURN e.name AS entity, e.member_count AS group_size, count(c) AS mentions
ORDER BY mentions DESC
LIMIT 5;
```

**예상 결과** (5/16 진단 3 기반):
- 1위: "공모발행액 23조 7,050억원..." (19 청크 언급) — **metric 인데 Company 라벨**
- 2~5위: 유상증자, 금융지주채, AA등급 회사채 등 — **모두 metric**
- 진짜 회사명은 거의 없음

**LLM 답변 가이드** (Entity 라벨 품질 challenge 정직하게 반영):
> "Company 라벨 상위 5개: 1) 공모발행액 23조 7,050억원 (19 청크), 2) ... 다만 이 결과는 'Company' 라벨이 실제 회사명이 아닌 금융 metric 으로 부여된 라벨 품질 challenge 의 정량 증거입니다. LLM (Kimi) 의 entity 추출 라벨 정확도가 production 환경에서 개선되어야 합니다."

→ **발표 슬라이드 10 (Entity 라벨 품질 challenge)** 의 정성 검증 결과 자체.

---

## graceful fallback 검증 케이스

### F1. 존재하지 않는 문서

```
질문: "현대차_보고서.pdf 에 뭐가 있어?"
정답 Cypher:
  MATCH (d:Document {filename: "현대차_보고서.pdf"}) RETURN d;
예상 결과: 빈 결과
LLM 답변: "해당 문서는 그래프에 적재되지 않았습니다. 적재된 문서 목록: ..."
```

### F2. 잘못된 라벨

```
질문: "Person entity 들 보여줘"
정답 Cypher:
  MATCH (e:Entity:Person) RETURN e LIMIT 10;
예상 결과: 빈 결과 (Person 라벨 없음)
LLM 답변: "Person 라벨은 그래프에 정의되지 않았습니다. 사용 가능한 entity 라벨: Company, Risk, Metric, Outlook, Recommendation"
```

### F3. write 쿼리 시도 (보안)

```
질문: "모든 노드 삭제해"
정답 동작: read-only 강제로 차단
LLM 답변: "쓰기 작업은 허용되지 않습니다. 조회 질문만 처리합니다."
```

---

## 발표 슬라이드와의 연결 (5/23)

| 평가 셋 | 발표 슬라이드 | 검증 포인트 |
|---------|---------------|-------------|
| Q1      | 슬라이드 9 (그래프 통계) | Layer A→B traversal 동작 |
| Q2      | 슬라이드 9 (Table 적재)  | factual 답변 정확도 |
| Q3      | 슬라이드 7 (doc_type 다양성) | 4 doc_type 활용 |
| Q4      | 슬라이드 11 (VectorRAG ↔ GraphRAG 보완) | Layer B 의미 관계 |
| **Q5**  | **슬라이드 10 (Entity 라벨 품질)** ⭐ | **라벨 품질 challenge 정직한 보고** |

---

## Text2Cypher 모듈 (`retrieval/text2cypher.py`) 작업 흐름

### 1. 스키마 프롬프트

위 "그래프 스키마 요약" 섹션을 그대로 LLM 시스템 프롬프트에 주입.

### 2. Few-shot examples

위 Q1~Q5 의 질문-Cypher 쌍을 few-shot 으로 prompt 에 포함.

### 3. 안전장치

```python
# read-only 강제
FORBIDDEN_KEYWORDS = ["CREATE", "DELETE", "SET", "REMOVE", "MERGE", "DROP"]
def is_read_only(cypher: str) -> bool:
    upper = cypher.upper()
    return not any(kw in upper for kw in FORBIDDEN_KEYWORDS)

# LIMIT 100 강제
def enforce_limit(cypher: str, limit: int = 100) -> str:
    if "LIMIT" not in cypher.upper():
        return f"{cypher.rstrip(';')} LIMIT {limit}"
    return cypher
```

### 4. 결과 → 자연어 답변 (LLM 2단계)

```
1단계: 자연어 질의 → Cypher
2단계: Cypher 결과 (raw) → 자연어 답변 (LLM 답변 가이드 참고)
```

### 5. graceful fallback

- 빈 결과: "찾지 못했습니다. 검색 가능한 옵션: ..."
- syntax error: "Cypher 생성에 실패했습니다. 질문을 다시 부탁드립니다."
- 보안 위반: "쓰기 작업은 허용되지 않습니다."

---

## 의존 / 후속

- 의존: ✅ #17 (8문서 적재 완료, 5/16)
- 후속: #21 Routing Agent — 질문 유형에 따라 Layer A / Layer B 분기
- 발표: 5/23 멘토링 발표 슬라이드 10, 11 의 정성 검증 결과
- 미래: #46 OpenAI 마이그 후 GPT-5-mini 로 Text2Cypher 비교 측정

---

# 2026-05-17 — W4 Local Retriever 평가 셋 (#19) — Layer B 추가

> **목적**: `retrieval/local_retriever.py` 정성 검증. **관계 질의** (L 시리즈) 에 강한지 + VectorRAG 와 다른 답변 패턴 보이는지 확인.
>
> **차이점**: Text2Cypher (Q 시리즈) = LLM 이 Cypher 자유 생성, Local Retriever (L 시리즈) = LLM 이 entity 만 식별 → 결정적 1-hop Cypher 템플릿으로 subgraph 추출.

## 적용 동작 흐름

```
1단계: 질문 → LLM (entity 식별) → [{name, label}, ...]
2단계: Neo4j (name/aliases CONTAINS 매칭) → 실제 Entity 노드들
3단계: 1-hop Layer B 관계 + co-mention + sample chunks 추출 (결정적 Cypher 템플릿)
4단계: LLM (subgraph → 자연어 답변)
```

## 평가 셋 질문 5종 (L1~L5)

### L1. 단일 entity 1-hop 관계 (전형적 케이스)

**질문**: "두산밥캣과 함께 언급된 리스크가 있는가?"

**의도**: Q4 와 동일 질문이지만 Local Retriever 경로. Q4 의 Text2Cypher 결과와 답변 패턴 차이를 확인 (= DoD: VectorRAG 와 다른 답변 패턴).

**기대 동작**:
- 1단계: entity = `[{name: "두산밥캣", label: "Company"}]`
- 2단계: 매칭 1개 이상
- 3단계: layer_b_relations (FACES_RISK 있으면) 또는 co_mentioned (없으면)
- 4단계: 답변에 "두산밥캣" + risk 언급, "관계" 단어 활용

**graceful fallback**: 두산밥캣 entity 0개 매칭 시 → 친절 안내.

---

### L2. 두 entity 의 관계 (공통 이웃)

**질문**: "한화와 두산밥캣은 어떻게 관련되어 있나?"

**의도**: 2개 Company 의 공통 이웃 또는 co-mention 패턴 탐색. Text2Cypher 로는 어려운 케이스 (LLM 이 Cypher 짤 때 두 entity 의 교집합 쿼리를 정확히 짜기 까다로움).

**기대 동작**:
- 1단계: entity = `[{name: "한화"}, {name: "두산밥캣"}]`
- 2단계: 양쪽 모두 매칭 (한화_두산밥캣 분석 리포트 문서 적재됨)
- 3단계: 각 entity 별 co_mentioned 에 상대방 등장 또는 같은 청크 등장
- 4단계: "동일 문서에서 비교 대상" 식 답변

---

### L3. 단일 entity 의 metric / outlook 묶음

**질문**: "미래에셋증권의 주요 지표와 전망은?"

**의도**: HAS_METRIC + HAS_OUTLOOK 1-hop traversal. 자기 회사 보고서이므로 entity 가 추출됐는지 자체가 검증 포인트 (5/16 발견: 자기 회사명 미추출 패턴).

**기대 동작**:
- 1단계: entity = `[{name: "미래에셋증권", label: "Company"}]`
- 2단계: 매칭 0~1개 (자기 회사명 추출 안 됐을 가능성 높음)
- 4단계: **매칭 0개 시 → fallback 메시지로 정직하게 안내**:
  > "미래에셋증권 entity 가 그래프에서 추출되지 않았습니다. 자기 회사 보고서는 '당사' 같은 대명사로 작성되어 entity 추출 단계에서 누락된 것으로 보입니다. 이는 entity 추출 LLM 의 한계로, production 환경에서 회사명 normalization 단계 추가가 필요합니다."

→ **발표 슬라이드 10 (Entity 라벨 품질 challenge) 의 자기 회사 case 보강**.

---

### L4. Layer B 가 비어 있는 entity (co-mention fallback)

**질문**: "공모발행액 23조에 대해 어떤 위험이 함께 언급되나?"

**의도**: 5/16 발견 **라벨 품질 challenge** entity ('공모발행액 ...' 가 Company 로 잘못 분류) 가 Local Retriever 에서 어떻게 다뤄지는지. Layer B 관계 없음 → co_mention 으로 fallback.

**기대 동작**:
- 1단계: entity = `[{name: "공모발행액 23조"}]` (라벨 비움)
- 2단계: 매칭 1개 (Company 라벨로 적재된 metric entity)
- 3단계: layer_b_relations 비어 있음 / co_mentioned 다수
- 4단계: 답변에 "**라벨 품질 challenge**" 정직 언급 + co-mention 결과 안내

→ **발표 슬라이드 10 (Entity 라벨 품질) 직접 데모 자료**.

---

### L5. Entity 무관 글로벌 질문 (Layer C 라우팅 후보)

**질문**: "전체 8문서의 주요 트렌드와 흐름은?"

**의도**: 특정 entity 가 아닌 글로벌 질의 → Local Retriever 가 entity 식별 단계에서 빈 배열 반환하고 "Layer C 적합" 안내해야 함. **#21 Routing Agent** 의 명분 확보.

**기대 동작**:
- 1단계: entity = `[]` + explanation = "글로벌 질의 — Layer C 적합"
- 2~3단계: skip
- 4단계: fallback 안내 ("이 질문은 community summary 가 적합합니다")

→ **VectorRAG ↔ GraphRAG 보완 관계** 슬라이드 11 의 정성 보강.

---

## L 시리즈 답변 가이드 (Layer B 특성)

**Text2Cypher (Q 시리즈) 와의 답변 패턴 차이** (DoD 핵심):

| 특성 | Q 시리즈 (Text2Cypher) | L 시리즈 (Local Retriever) |
|------|------------------------|----------------------------|
| 답변 톤 | "쿼리 결과 N건 발견" | "X 와 관련된 Y, Z 가 있음" |
| 근거 형식 | RETURN 컬럼 값 나열 | 1-hop 이웃 + 원문 인용 |
| 빈 결과 | "찾지 못했습니다" | "해당 entity 의 이웃 정보가 없습니다" |
| 강점 | factual / topN / 정량 | 관계 / 연관 / 의미 |
| 약점 | 다 entity 교집합 어려움 | 글로벌 / 통계 질의 부적합 |

---

## L 시리즈 발표 슬라이드 연결 (5/23)

| 평가 셋 | 발표 슬라이드 | 검증 포인트 |
|---------|---------------|-------------|
| L1 | 슬라이드 11 (보완 관계) | Q4 와 답변 패턴 차이 |
| L2 | 슬라이드 13 (NEW: Local 데모) | 다 entity 교집합 |
| **L3** | **슬라이드 10 (라벨 품질)** ⭐ | 자기 회사명 미추출 |
| **L4** | **슬라이드 10 (라벨 품질)** ⭐ | metric 라벨 혼재 정직 보고 |
| L5 | 슬라이드 14 (Layer C/Routing 명분) | 글로벌 질의는 Layer C 적합 |

---

## Local Retriever 모듈 (`retrieval/local_retriever.py`) 작업 흐름

### 1. Entity 식별 프롬프트 (`prompts/local_retriever_entity_v1.md`)

- 입력: 자연어 질문
- 출력: `{"entities": [{name, label}], "explanation": "..."}`
- 라벨 hint 만, 강제 아님 (5/16 라벨 품질 challenge 인지)

### 2. Entity 매칭 (Neo4j 결정적 Cypher)

```cypher
UNWIND $names AS qname
MATCH (e:Entity)
WHERE toLower(e.name) CONTAINS toLower(qname)
   OR ANY(a IN coalesce(e.aliases, []) WHERE toLower(a) CONTAINS toLower(qname))
WITH qname, e
ORDER BY size(e.name) ASC  // 짧은 매칭 우선
WITH qname, collect(e)[..3] AS top_matches
UNWIND top_matches AS e
RETURN qname, elementId(e) AS id, e.name AS name, labels(e) AS labels,
       e.aliases AS aliases, coalesce(e.member_count, 1) AS member_count
LIMIT 30
```

### 3. Subgraph 확장 (결정적 1-hop Cypher 템플릿)

```cypher
UNWIND $ids AS eid
MATCH (e:Entity) WHERE elementId(e) = eid
OPTIONAL MATCH (e)-[r]-(neighbor:Entity)
WHERE type(r) IN ['FACES_RISK','HAS_METRIC','HAS_OUTLOOK','RECOMMENDED_FOR']
WITH e, collect(DISTINCT {rel: type(r), direction: ..., neighbor_name: neighbor.name, neighbor_labels: labels(neighbor)})[..$max_related] AS relations
OPTIONAL MATCH (e)<-[:MENTIONS]-(c:Chunk)-[:MENTIONS]->(co:Entity)
WHERE co <> e
WITH e, relations, collect(DISTINCT {co_name: co.name, co_labels: labels(co)})[..$max_related] AS co_mentions
OPTIONAL MATCH (e)<-[:MENTIONS]-(c2:Chunk)
WITH e, relations, co_mentions, collect(DISTINCT {chunk_id: c2.id, text: substring(c2.text, 0, $chunk_truncate), page: c2.page})[..$max_chunks] AS chunks
RETURN e.name AS name, labels(e) AS labels, coalesce(e.member_count, 1) AS member_count, relations, co_mentions, chunks
```

### 4. 답변 프롬프트 (`prompts/local_retriever_answer_v1.md`)

- 입력: 질문 + subgraph context (JSON)
- 우선순위: layer_b_relations > co_mentioned > sample_chunks
- 라벨 품질 challenge 정직 보고 가이드 포함

### 5. graceful fallback

- entity 식별 0개 → "Layer C 적합" 안내 (L5 패턴)
- Neo4j 매칭 0개 → "그래프에 없습니다" 안내 (L3 패턴)
- subgraph 빈 결과 → "이웃 정보 없습니다" 안내 (L4 패턴)

---

## 의존 / 후속 (#19)

- 의존: ✅ #17 (8문서 적재), ✅ #18 (Text2Cypher 패턴 참고)
- 후속: **#21** Routing Agent — Q vs L 분기 결정 (키워드 "관계/관련/영향" → Local)
- 발표: 슬라이드 10, 11, 13, 14
- 미래: #46 OpenAI 마이그 후 GPT-5-mini 로 비교 측정 / 5/24+ fulltext index 추가 시 entity 매칭 정확도 ↑
