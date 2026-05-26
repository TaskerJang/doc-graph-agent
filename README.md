

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Neo4j](https://img.shields.io/badge/Neo4j-LPG-008CC1?style=flat-square&logo=neo4j&logoColor=white)](https://neo4j.com/)

---

## 프로젝트 개요

doc-graph-agent는 한국 금융 문서 8건(한화, DS시황, 미래에셋 1Q~4Q, 농협, 금감원)을 대상으로 Layer A/B/C로 분리된 GraphRAG 시스템을 구축하고, 80개의 QA로 적용 영역을 진단한 프로젝트입니다.

## 한 줄 요약

> GraphRAG는 모든 질의에 답하는 시스템이 아니라, 특정 영역에서 RAG가 구조적으로 접근 불가한 답을 제공하는 시스템이다.

## 핵심 발견

6주 동안 doc-graph-agent를 처음부터 구축하고, 동일 8개 문서·80 QA로 측정한 결과:

### GraphRAG가 빛나는 영역

- **`negative` (부재 증명)** — "문서에 X가 없다"를 증명하는 질의. 그래프 구조 자체가 답을 만듦.
- **`limitation` (메타 질의)** — 시스템이 무엇을 알고 모르는지에 대한 질의.

두 영역 모두 RAG가 구조적으로 접근 불가능한 영역입니다.

### GraphRAG가 무너진 영역

- **Entity 라벨 오분류** — 전처리 LLM 품질이 시스템 전체를 결정
- **Metric 노드 미생성** — 수치 entity 추출 실패
- **OCR 글자 깨짐** — 파싱 인프라의 한계
- **Layer C 핵심 로직 미구현** — Community Summary는 진입점만 박힌 상태

> **결론**: 단일 시스템(GraphRAG든 BM25든)은 답이 아니다. Router + Graph + Vector + Community Summary가 통합된 Hybrid 아키텍처가 production 정답.

전체 분석은 회고 글에서 → [Velog 회고록](https://velog.io/@taskerjang)

---

## 아키텍처

<img width="810" height="700" alt="image" src="https://github.com/user-attachments/assets/ad381a34-2d56-4c74-83b0-cb402fab1474" />

| Layer | 책임 | 적합 질의 유형 | 검색 전략 |
|---|---|---|---|
| **A: Document Structure** | 출처 추적, 원문 인용 | "X 문서의 Y는?" | Text-to-Cypher (read-only) |
| **B: Entity Interaction** | 의미 연결, 관계 탐색 | "A와 B의 관계는?" | Local Retriever + Subgraph |
| **C: Community/Topic** | 글로벌 요약 | "전체 흐름은?" | Community Summary |

Layer C는 진입점과 라우팅 분기까지 구현되어 있으며, Leiden community detection과 map-reduce 합성은 다음 단계입니다.

---

## 평가 설정

| 항목 | 값 |
|---|---|
| 평가셋 | 80 QA (VectorRAG 40 + GraphRAG 40) |
| 문서 corpus | 8 doc (한화, DS시황, 미래에셋 1Q~4Q, 농협, 금감원) |
| LLM | `openai/gpt-5-mini`, `moonshotai/kimi-k2.5` |
| Judge | `anthropic/claude-haiku-4.5` |
| 메트릭 | ROUGE-L, 수치 정확도, Faithfulness, Correctness, Routing Accuracy |

---

## 빠른 시작

### 1. 환경 설정

```bash
uv sync
cp .env.example .env  # OpenRouter 키 + Neo4j 접속 정보 입력
```

### 2. Neo4j (DozerDB) 시작

```bash
docker compose up -d neo4j
```

### 3. 8개 문서 인덱싱

```bash
uv run python scripts/run_ingestion.py
uv run python scripts/load_graph.py
```

### 4. 80 QA 측정

```bash
uv run python scripts/run_qa_eval.py \
  --llm-model "moonshotai/kimi-k2.5" \
  --judge-model "anthropic/claude-haiku-4.5" \
  --qa-set both \
  --tag my_run
```

### 5. 측정 결과를 표로 생성

```bash
uv run python scripts/make_report_tables.py \
  --gpt5 eval/results/qa_eval_openai_gpt5mini_*.json \
  --kimi eval/results/qa_eval_kimi_k25_*.json \
  --out  eval/results/report_tables.md
```

---

## 디렉토리 구조

```
doc-graph-agent/
├── docs/
│   ├── adr/                    # Architecture Decision Records
│   ├── ontology/               # Layer A/B/C 도메인 온톨로지
│   └── weekly-log/             # 주차별 진척
├── ingestion/                  # 파싱 + 청킹 (PDF/DOCX/HWP/OCR)
├── kg/                         # Knowledge Graph 구축
│   ├── extractor.py            #   Entity 추출
│   ├── linker.py               #   Entity Linking (NED)
│   ├── deduplicator.py         #   중복 제거 (cosine 0.92)
│   └── loader.py               #   Neo4j 적재
├── retrieval/                  # Layer A/B/C 검색 + Routing
│   ├── text2cypher.py          #   Layer A
│   ├── local_retriever.py      #   Layer B
│   ├── community_summary.py    #   Layer C
│   └── router.py               #   Routing Agent
├── observability/              # Opik 트레이싱
├── eval/
│   ├── dataset/qa_pairs.json   # 평가셋 (80 QA)
│   └── results/                # 측정 결과 JSON + 표
├── scripts/
│   ├── run_qa_eval.py          # 80 QA 측정 자동화
│   └── make_report_tables.py   # 결과 → 표 생성
├── tests/
├── AGENTS.md                   # Codex / Cursor 컨텍스트
└── CLAUDE.md                   # Claude Code 컨텍스트
```

---

## 기술 스택

- **Core**: Python 3.11+, Neo4j (DozerDB), Docker Compose
- **LLM / Embedding**: OpenAI `gpt-5-mini`, OpenRouter, BGE-M3
- **Observability**: Opik
- **Build / Test**: uv, Pytest

---

## 브랜치 / 커밋 컨벤션

### 브랜치 전략

| 브랜치 | 용도 |
|---|---|
| `main` | 발표·제출용 |
| `dev` | 개발 통합 |
| `feat/{이슈}-{kebab-case}` | 기능 (예: `feat/12-text2cypher`) |
| `fix/...` · `docs/...` · `refactor/...` · `chore/...` | 용도별 접두어 |

### 커밋 메시지

Conventional Commits — `태그(스코프): #이슈 설명`

```
feat(kg): #5 Entity Linking에 Cosine similarity dedup 적용
fix(retrieval): #12 Text2Cypher 결과 1000행 제한 추가
docs(adr): #3 Layer 분리 의사결정 ADR 추가
```
