# 2026-05-17 — W4 Local Retriever (#19) 작업 일지

> **WBS 1.14** — W4 Layer B: Local Retriever
> **이슈**: #19
> **브랜치**: `feat/19-local-retriever`

## 작업 컨텍스트

5/16 토 PR #48 (#18 Text2Cypher 8/8 PASS) 머지 완료 후 W4 두 번째 retrieval 작업.

text2cypher.py 패턴 (LLM 2단계 호출 + JSON 응답 + tenacity 재시도 + @track + graceful fallback) 을 그대로 재활용하되, **LLM 이 Cypher 를 자유 생성하는 대신 entity 만 식별**하고 subgraph 는 결정적 1-hop Cypher 템플릿으로 추출하는 패턴.

## 레퍼런스

- **Microsoft GraphRAG Local Search** — entity 를 graph 진입점 (access point) 으로 활용, connected entities + relationships + community reports + chunks 를 컨텍스트로 합성하는 컨셉 차용.
- **Tomaz Bratanic (Neo4j Developer Blog)** — Implementing 'From Local to Global' GraphRAG with Neo4j and LangChain — graph 구축/검색의 Neo4j 구체 패턴 참고.
- **회사 레포** `doc-summary-agent/summarizer/llm.py` — LLM 호출 / JSON 강제 / 재시도 패턴 (kg/extractor.py 가 이미 정합).

## 차이점 — Text2Cypher (Q*) vs Local Retriever (L*)

| 특성 | Q (Text2Cypher) | L (Local Retriever) |
|------|------------------|---------------------|
| LLM 역할 | Cypher 자유 생성 | entity 만 식별 |
| Cypher | LLM 생성 (다양) | 결정적 1-hop 템플릿 |
| 강점 | factual / topN / 정량 | 관계 / 연관 / 의미 |
| 약점 | 다 entity 교집합 | 글로벌 / 통계 질의 |
| 안전장치 | read-only 강제 + LIMIT | parameterized (사용자 입력 escape) |

## 변경 사항

### 신규 파일

- `retrieval/local_retriever.py` (≈ 540 lines) — Local Retriever 메인 모듈
- `retrieval/prompts/local_retriever_entity_v1.md` — entity 식별 system prompt (5 few-shot 예시)
- `retrieval/prompts/local_retriever_answer_v1.md` — 답변 생성 system prompt (4 few-shot 예시)

### 수정 파일

- `retrieval/__init__.py` — `local_retrieve`, `LocalRetrieverResult`, `LocalRetrieverError` 추가 export
- `retrieval/eval_set.md` — L1~L5 섹션 추가 (~150 lines)
- `scripts/run_w4_eval.py` — L 케이스 5개 추가 + suite 필터 (`--suite local`) + Local Retriever 분기 평가 로직

## 평가 셋 L1~L5 — 정성 검증 케이스

| ID | 카테고리 | 질문 | 검증 포인트 |
|----|---------|------|------------|
| L1 | relation | 두산밥캣과 함께 언급된 리스크는? | Q4 와 답변 패턴 차이 (subgraph 활용) |
| L2 | two-entity | 한화와 두산밥캣은 어떻게 관련되어 있나? | 두 entity 교집합 (Text2Cypher 어려운 케이스) |
| L3 | self-company | 미래에셋증권의 주요 지표와 전망은? | ⭐ 자기 회사명 미추출 graceful (슬라이드 10 보강) |
| L4 | label-quality | 공모발행액 23조에 대해 어떤 위험이 함께 언급? | ⭐ 라벨 품질 challenge 정직 보고 (슬라이드 10) |
| L5 | global | 전체 8문서의 주요 트렌드는? | Layer C 라우팅 명분 (슬라이드 14) |

## 실행 방법

```cmd
:: 전체 (Q* + F* + L*)
uv run python -m scripts.run_w4_eval

:: Local Retriever 만
uv run python -m scripts.run_w4_eval --suite local

:: 1개만
uv run python -m scripts.run_w4_eval --case L3

:: JSON 박제
uv run python -m scripts.run_w4_eval --suite local --json eval/w4_local_2026-05-17.json
```

## DoD (#19)

- [ ] 관계 질의 (L1, L2) 에서 Vector RAG / Text2Cypher 와 다른 답변 패턴 (subgraph 정보 활용) — **본인 정성 확인**
- [ ] 평균 응답 시간 < 5초 — **본인 측정 결과 박제**
- [ ] graceful fallback (L3 매칭 0개, L4 라벨 challenge, L5 글로벌)

## 정성 검증 결과 — TBD (본인 실행 후 채우기)

```
| ID | category | verdict | identified | matched | relations | chunks | elapsed |
|----|----------|---------|-----------:|--------:|----------:|-------:|--------:|
| L1 | ...      | ...     |          ? |       ? |         ? |      ? |     ?s |
| L2 | ...      | ...     |          ? |       ? |         ? |      ? |     ?s |
| L3 | ...      | ...     |          ? |       ? |         ? |      ? |     ?s |
| L4 | ...      | ...     |          ? |       ? |         ? |      ? |     ?s |
| L5 | ...      | ...     |          ? |       ? |         ? |      ? |     ?s |

Local Retriever 평균 응답: ?s (DoD: < 5초)
```

## 시행착오 박제 — 실행 후 추가 예정

- Entity 매칭 시 fulltext index 없이 `CONTAINS` 만 쓸 때 정확도 한계 → 5/24+ fulltext index 추가 후 비교 측정
- LLM (Kimi) 의 entity 라벨 hint 정확도 — 빈 라벨 hint 도 OK 라고 프롬프트에 명시
- subgraph 크기 제한 (MAX_ENTITIES_TO_EXPAND=5, MAX_RELATED_PER_ENTITY=15) 의 적정성

## 발표 슬라이드 연결 (5/23)

- **슬라이드 10 (Entity 라벨 품질)** ← L3, L4 정성 검증 보강
- **슬라이드 11 (VectorRAG ↔ GraphRAG 보완)** ← L1 (Q4 와 패턴 차이)
- **슬라이드 13 (NEW: Local Retriever 데모)** ← L1 또는 L2 시연
- **슬라이드 14 (Routing 명분)** ← L5 글로벌 질의 fallback

## 의존 / 후속

- 의존: ✅ #17 (8문서 적재 완료, 5/16), ✅ #18 (Text2Cypher 패턴 참고, PR #48)
- 후속: **#21** Routing Agent — Q vs L 분기 (키워드 "관계/관련/영향" → Local)
- 미래: #46 OpenAI 마이그 후 GPT-5-mini 로 비교 측정 / fulltext index 추가
