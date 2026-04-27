<div align="center">

# 📊 doc-graph-agent

**VectorRAG 프로젝트를 GraphRAG로 재구성하며 배운 것**

SEOCHO Mentoring Program 2026 Spring · 6주 개인 프로젝트

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Neo4j](https://img.shields.io/badge/Neo4j-LPG-008CC1?logo=neo4j&logoColor=white)](https://neo4j.com/)
[![Chainlit](https://img.shields.io/badge/Chainlit-2.11-ff69b4)](https://chainlit.io/)
[![Opik](https://img.shields.io/badge/Opik-Tracing-262626)](https://www.comet.com/site/products/opik/)

</div>

---

## 🎯 프로젝트 정체성

회사에서 구축한 [`doc-summary-agent`](https://github.com/TaskerJang/doc-summary-agent) (VectorRAG, BM25 + bge-m3 + RRF + Reranker)를 **SEOCHO 플랫폼의 Layer A/B/C 구조**에 맞춰 GraphRAG로 재구성한다.

UI·파싱·평가 셋 등 기반 자산은 재활용하고, **Retrieval 코어와 Knowledge Graph 구축 파이프라인을 새로 설계**한다.

### 발표 서사 5단 구성

1. **Before** — 기존 Document Agent의 한계 (Completeness 1.25/5, Faithfulness 77.5%)
2. **Why GraphRAG** — 어떤 질문 유형에서 VectorRAG의 구조적 한계가 드러났는가
3. **How** — Layer A/B/C 구조 적용 과정과 의사결정 (`docs/adr/`)
4. **After** — 동일 평가 셋(40 QA) 기준 측정 결과
5. **Lessons** — 잘 된 것, 안 된 것, 다음 단계

---

## 🏗️ 아키텍처: SEOCHO 3-Layer

| Layer | 책임 | 적합한 질문 유형 | 검색 전략 |
|---|---|---|---|
| **A: Document Structure** | 출처 추적, 원문 인용 | "X 문서의 Y 섹션에 무엇이 있나" | Text-to-Cypher |
| **B: Entity Interaction** | 의미 연결, 관계 탐색 | "A와 B는 어떻게 관련되나" | Local Retriever + Subgraph |
| **C: Community/Topic** | 글로벌 요약, 주제 통합 | "전체적으로 어떤 흐름인가" | Community Summary |

---

## 🔁 재활용 vs 신규 설계

| 재활용 (기존 doc-summary-agent) | 신규 설계 (멘토링 핵심) |
|---|---|
| Chainlit UI 레이어 | Knowledge Graph 구축 파이프라인 |
| 파싱 인프라 (PDF/DOCX/HWP, OCR) | Entity 추출 + Linking + Dedup |
| Markdown 구조 청킹 | Layer A/B/C 라우팅 Agent |
| **평가 셋 (`qa_pairs.json`, 40개)** | Cypher / Text2Cypher 쿼리 레이어 |
| 평가 메트릭 (ROUGE, 수치 정확도, Faithfulness, Completeness) | Opik 기반 트레이싱·평가 |

> 동일 평가 셋을 그대로 재사용하는 것이 핵심이다. Before/After 비교의 신뢰성이 여기서 결정된다.

---

## 📊 Before 베이스라인 (기존 레포 측정 결과)

> `prompt_v2_bm25`, `chunk_size=500`, `overlap=50`, QA 40개 기준.

| 지표 | Before (VectorRAG) | After (GraphRAG) |
|---|---|---|
| ROUGE-L | 0.2929 | TBD |
| 수치 정확도 | 0.7102 | TBD |
| Faithfulness | 31/40 (77.5%) | TBD |
| **Completeness** | **1.25 / 5** | **TBD** |
| Conciseness | 3.90 / 5 | TBD |

특히 **Completeness 1.25/5** — 흩어진 정보를 통합해야 하는 질문에서 VectorRAG가 구조적으로 약하다는 신호. GraphRAG의 Layer C (Community Summary)가 가장 직접적으로 겨냥하는 지점이다.

---

## 🗓️ 6주 로드맵

| Week | 주제 | 산출물 |
|---|---|---|
| W1 (04.18~) | Foundation | 레포 부트스트랩, Before 베이스라인 재측정 |
| W2 (04.25~) | Ontology | Document/Entity/Community 3계층 스키마 |
| W3 (05.02~) | KG Build | Entity 추출 + Linking + Neo4j 적재 |
| W4 (05.09~) | Retrieval | Layer A/B/C + Routing Agent |
| W5 (05.16~) | Observability | Opik 트레이싱 + 동일 셋 평가 |
| W6 (05.23~) | Showcase | Before/After 발표 자료 |

주차별 진척은 `docs/weekly-log/`에 기록한다.

---

## 📂 디렉토리 구조

```
doc-graph-agent/
├── docs/
│   ├── before-after.md         # 기존 레포 한계 → GraphRAG 매핑 표
│   ├── ontology/               # Layer A/B/C 도메인 온톨로지 설계
│   ├── adr/                    # Architecture Decision Records
│   └── weekly-log/             # 주차별 진척 (블로그 글과 짝)
├── ingestion/                  # 파싱 + 청킹 (기존 자산 포팅)
├── kg/                         # Knowledge Graph 구축 — 신규
├── retrieval/                  # Layer A/B/C 검색 — 신규
├── agent/                      # 라우팅 + Debate Pool — 신규
├── observability/              # Opik 트레이싱 — 신규
├── eval/                       # 평가 (기존 셋 재사용)
├── ui/                         # Chainlit UI (기존 자산 포팅)
├── tests/
├── AGENTS.md                   # Codex / Cursor 컨텍스트
└── CLAUDE.md                   # Claude Code 컨텍스트
```

---

## 🌱 브랜치 전략

| 브랜치 | 용도 |
|---|---|
| `main` | 발표·제출용 |
| `dev` | 개발 통합 |
| `feat/{이슈번호}-{kebab-case}` | 기능 단위 (예: `feat/12-text2cypher`) |
| `fix/...` · `docs/...` · `refactor/...` · `chore/...` | 용도별 접두어 |

---

## 📝 커밋 컨벤션

Conventional Commits 기반의 `태그(스코프): #이슈 설명` 형식.

```
feat(kg): #5 Entity Linking에 Cosine similarity dedup 적용
fix(retrieval): #12 Text2Cypher 결과 1000행 제한 추가
docs(adr): #3 Layer 분리 의사결정 ADR 추가
```

---

## 🔗 관련 링크

- 기존 레포 (Before): [doc-summary-agent](https://github.com/TaskerJang/doc-summary-agent)
- 멘토링 블로그 시리즈: [tasker_dev.log](https://velog.io/@taskerjang)
- 멘토: 정이태 (Hardy)

---

<div align="center">
<sub>Built during SEOCHO Mentoring 2026 Spring</sub>
</div>
