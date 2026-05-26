<div align="center">

<img src="https://img.shields.io/badge/SEOCHO-Mentoring%202026%20Spring-6c63ff?style=for-the-badge" alt="SEOCHO" />

# 📊 doc-graph-agent

### *GraphRAG는 어디서 빛나고 어디서 무너지는가*

**80 QA로 진단한 GraphRAG의 적용 영역 지도**

<br>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Neo4j](https://img.shields.io/badge/Neo4j-LPG-008CC1?style=flat-square&logo=neo4j&logoColor=white)](https://neo4j.com/)
[![Chainlit](https://img.shields.io/badge/Chainlit-2.11-ff69b4?style=flat-square)](https://chainlit.io/)
[![Opik](https://img.shields.io/badge/Opik-Tracing-262626?style=flat-square)](https://www.comet.com/site/products/opik/)
[![OpenAI](https://img.shields.io/badge/OpenAI-gpt--5--mini-412991?style=flat-square&logo=openai&logoColor=white)](https://openai.com/)
[![Moonshot](https://img.shields.io/badge/Moonshot-kimi--k2.5-orange?style=flat-square)](https://www.moonshot.ai/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

[![PRs](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)](https://github.com/TaskerJang/doc-graph-agent/pulls)
[![Velog](https://img.shields.io/badge/Velog-26%20posts-20C997?style=flat-square&logo=velog&logoColor=white)](https://velog.io/@taskerjang)
[![Mentor](https://img.shields.io/badge/Mentor-Hardy%20%EC%A0%95%EC%9D%B4%ED%83%9C-blueviolet?style=flat-square)](https://github.com/tteon)


</br>

---

## 🌟 한 줄 요약

> **GraphRAG는 *모든 질의*에 답하는 시스템이 아니라, *특정 영역*에서 RAG가 구조적으로 접근 불가한 답을 제공하는 시스템이다.**
> 80 QA 측정으로 그 영역을 정량 식별하고, *Hybrid 아키텍처*가 production 정답임을 정량 증명한다.

---

## 🎯 핵심 발견

6주 동안 doc-graph-agent를 처음부터 구축하고, 동일 8개 문서·80 QA·2개 LLM(`gpt-5-mini`, `kimi-k2.5`)으로 측정한 결과:

<table>
<tr>
<td width="50%" valign="top">

### ✅ GraphRAG가 *빛나는* 영역

| Pattern | Correctness | Faithful |
|---|---|---|
| `negative` (부재 증명) | **5.00 / 5** | **75~100%** |
| `limitation` (메타 질의) | **4.50 / 5** | **50%** |
| `filter_agg` (corpus 집계) | 1.60 / 5 | 0%* |

> 그래프 구조 자체가 답을 만드는 영역.
> RAG가 *구조적으로 접근 불가*한 질의.

</td>
<td width="50%" valign="top">

### ❌ GraphRAG가 *무너진* 영역

| 원인 | 영향 QA |
|---|---|
| Entity 라벨 오분류 | ~40 건 |
| Metric 노드 미생성 | ~17 건 |
| OCR 글자 깨짐 | 11 건 |
| Layer C 핵심 로직 미구현 | 6 건 |

> 전처리 LLM 품질 + 파싱 인프라가
> 시스템 전체를 결정.

</td>
</tr>
</table>

<sub>* filter_agg는 1건 만점(graph_031) — 전체 corpus 집계는 본질적으로 GraphRAG 영역이나 entity 추출 품질이 발목.</sub>

> 🔑 **결론**: 단일 시스템(GraphRAG든 BM25든)은 답이 아니다. **Router + Graph + Vector + Community Summary가 통합된 Hybrid 아키텍처**가 production 정답.

📖 전체 분석은 회고 글에서 → [**Velog 회고록**](https://velog.io/@taskerjang)

---

## 🏗️ 아키텍처

<img width="810" height="700" alt="image" src="https://github.com/user-attachments/assets/ad381a34-2d56-4c74-83b0-cb402fab1474" />




| Layer | 책임 | 적합 질의 유형 | 검색 전략 | 본 측정 결과 |
|---|---|---|---|---|
| **🔍 A: Document Structure** | 출처 추적, 원문 인용 | "X 문서의 Y는?" | Text-to-Cypher (read-only) | filter_agg 1/5 ✅ |
| **🔗 B: Entity Interaction** | 의미 연결, 관계 탐색 | "A와 B의 관계는?" | Local Retriever + Subgraph | 1hop 0/10 ❌ (전처리 한계) |
| **🌐 C: Community/Topic** | 글로벌 요약 | "전체 흐름은?" | Community Summary | stub — 진입점만 박힘 |

> Layer C는 **진입점 + 라우팅 분기 + stub 안내**까지 구현 완료. Leiden community detection + map-reduce 합성은 다음 단계.

---

## 📊 측정 결과 — 80 QA 기준

### 통제 조건

| 항목 | 값 |
|---|---|
| 평가셋 | 80 QA (VectorRAG 40 + GraphRAG 40) |
| 문서 corpus | 8 doc (한화, DS시황, 미래에셋 1Q~4Q, 농협, 금감원) |
| LLM | `openai/gpt-5-mini`, `moonshotai/kimi-k2.5` (각 1회) |
| Judge | `anthropic/claude-haiku-4.5` |
| 메트릭 | ROUGE-L, 수치 정확도, Faithfulness, Correctness, Routing Accuracy |

### 전체 그림 (kimi-k2.5 기준)

<div align="center">

| 지표 | 값 | 진단 |
|:---:|:---:|:---|
| 평균 Correctness | **1.41 / 5** | 전반적 부진 — *전처리 품질이 원인* |
| Faithful (%) | **5.0%** | 답변 생성 단계는 정직 |
| Routing Accuracy | **87.5%** | ✅ 의사결정 레이어는 정상 |
| 빈 응답 | **0 / 80** | ✅ 시스템 안정성 정상 |

</div>



## 🚀 빠른 시작

### 1️⃣ 환경 설정

```bash
# 의존성 설치
uv sync

# .env 파일 작성 — OpenRouter 키 + Neo4j 접속 정보
cp .env.example .env
```

### 2️⃣ Neo4j (DozerDB) 시작

```bash
docker compose up -d neo4j
```

### 3️⃣ 8개 문서 인덱싱

```bash
uv run python scripts/run_ingestion.py
uv run python scripts/load_graph.py
```

### 4️⃣ 80 QA 측정

```bash
uv run python scripts/run_qa_eval.py \
  --llm-model "moonshotai/kimi-k2.5" \
  --judge-model "anthropic/claude-haiku-4.5" \
  --qa-set both \
  --tag my_run
```

### 5️⃣ 측정 결과 → 표 생성

```bash
uv run python scripts/make_report_tables.py \
  --gpt5 eval/results/qa_eval_openai_gpt5mini_*.json \
  --kimi eval/results/qa_eval_kimi_k25_*.json \
  --out  eval/results/report_tables.md
```


---

## 📂 디렉토리 구조

```
doc-graph-agent/
├── 📁 docs/
│   ├── adr/                    # Architecture Decision Records
│   ├── ontology/               # Layer A/B/C 도메인 온톨로지
│   └── weekly-log/             # 주차별 진척 (블로그와 짝)
├── 📁 ingestion/               # 파싱 + 청킹 (PDF/DOCX/HWP/OCR)
├── 📁 kg/                      # Knowledge Graph 구축
│   ├── extractor.py            #   Entity 추출
│   ├── linker.py               #   Entity Linking (NED)
│   ├── deduplicator.py         #   중복 제거 (cosine 0.92)
│   └── loader.py               #   Neo4j 적재
├── 📁 retrieval/               # Layer A/B/C 검색 + Routing
│   ├── text2cypher.py          #   Layer A
│   ├── local_retriever.py      #   Layer B
│   ├── community_summary.py    #   Layer C (진입점만, 핵심 로직 stub)
│   └── router.py               #   Routing Agent
├── 📁 observability/           # Opik 트레이싱
├── 📁 eval/
│   ├── dataset/qa_pairs.json   # 평가셋 (80 QA)
│   └── results/                # 측정 결과 JSON + 표
├── 📁 scripts/
│   ├── run_qa_eval.py          # 80 QA 측정 자동화
│   └── make_report_tables.py   # 결과 → 표 5종 생성
├── 📁 tests/
├── AGENTS.md                   # Codex / Cursor 컨텍스트
└── CLAUDE.md                   # Claude Code 컨텍스트
```

---

## 🧪 기술 스택

<div align="center">

### Core
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-DozerDB-008CC1?style=for-the-badge&logo=neo4j&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)

### LLM / Embedding
![OpenAI](https://img.shields.io/badge/OpenAI-gpt--5--mini-412991?style=for-the-badge&logo=openai&logoColor=white)
![OpenRouter](https://img.shields.io/badge/OpenRouter-Multi--Model-FF6B6B?style=for-the-badge)
![BGE-M3](https://img.shields.io/badge/BGE--M3-Embedding-FFD93D?style=for-the-badge)

### Observability
![Opik](https://img.shields.io/badge/Opik-Tracing-262626?style=for-the-badge)

### Build / Test
![uv](https://img.shields.io/badge/uv-Package%20Manager-DE5FE9?style=for-the-badge)
![Pytest](https://img.shields.io/badge/Pytest-Testing-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)

</div>

---

## 🌱 브랜치 / 커밋 컨벤션

<details>
<summary><b>브랜치 전략</b></summary>

| 브랜치 | 용도 |
|---|---|
| `main` | 발표·제출용 |
| `dev` | 개발 통합 |
| `feat/{이슈}-{kebab-case}` | 기능 (예: `feat/12-text2cypher`) |
| `fix/...` · `docs/...` · `refactor/...` · `chore/...` | 용도별 접두어 |

</details>

<details>
<summary><b>커밋 메시지</b></summary>

Conventional Commits — `태그(스코프): #이슈 설명`

```
feat(kg): #5 Entity Linking에 Cosine similarity dedup 적용
fix(retrieval): #12 Text2Cypher 결과 1000행 제한 추가
docs(adr): #3 Layer 분리 의사결정 ADR 추가
```

</details>

---

## 📚 학습 자료 — Velog 26편

6주 동안 GraphRAG / Neo4j 학습을 블로그로 누적했습니다. 한국 GraphRAG 자료 공급 부족 환경에서 한국 개발자 커뮤니티의 *time saver* 가 되기를 바랍니다.

<table>
<tr>
<td width="50%" valign="top">

### 🟣 GraphRAG 시리즈 (15편)

- #1 KG와 LLM, 강력한 결합
- #2 지능형 시스템과 하이브리드 접근
- #3 온톨로지로 첫 KG 만들기
- #4 단일 → 다중 소스 통합
- #5 비구조화 데이터 추출
- #6 LLM으로 KG 구축
- #7 NED — W3 핵심
- ... 외 8편

</td>
<td width="50%" valign="top">

### 🔵 Neo4j 시리즈 (10편)

- #1 그래프 데이터 사이언스 개요
- #2 Python과 Neo4j 시작
- #3 Neo4j 데이터 임포트
- #4 Cypher 쿼리 언어
- #5 그래프 네트워크 시각화
- #6 ChatGPT로 Neo4j 보강
- #7 벡터 인덱스와 RAG
- ... 외 3편

</td>
</tr>
</table>

📖 전체 글: **[velog.io/@taskerjang](https://velog.io/@taskerjang)**

---

<br>

**🌸 Built during SEOCHO Mentoring 2026 Spring**

<sub>Made with ❤️ by [TaskerJang](https://github.com/TaskerJang) · Mentored by [Hardy](https://github.com/tteon)</sub>

<br>

![Stars](https://img.shields.io/github/stars/TaskerJang/doc-graph-agent?style=social)
![Forks](https://img.shields.io/github/forks/TaskerJang/doc-graph-agent?style=social)

</div>
