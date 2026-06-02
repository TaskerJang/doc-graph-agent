# doc-graph-agent 80 QA 측정 결과 — 보고서 첨부용 표

- gpt-5-mini 결과 파일: `qa_eval_openai_gpt5mini_80qa_20260526_004309.json`
- kimi-k2.5 결과 파일:  `qa_eval_kimi_k25_80qa_20260526_011755.json`

---

### Table 1. LLM 비교 — 동일 80 QA, 동일 시스템 (doc-graph-agent)

| 메트릭 | gpt-5-mini | kimi-k2.5 | 차이 |
|---|---|---|---|
| Correctness (/5) | 1.20 | 1.41 | +0.21 |
| Faithful (%) | 12.5% | 5.0% | -7.5p |
| Completeness (/5) | 1.21 | 1.30 | +0.09 |
| Conciseness (/5) | 1.69 | 1.34 | -0.35 |
| ROUGE-L | 0.071 | 0.078 | +0.007 |
| 수치 정확도 | 0.134 | 0.160 | +0.025 |
| Semantic Similarity | 0.366 | 0.470 | +0.104 |
| Entity Coverage | 0.014 | 0.223 | +0.209 |
| 빈 응답 | 0/80 | 0/80 | — |

> 두 모델 모두 정상 작동(빈 응답 0건). 평균 Correctness 차이는 0.21점으로 미미 — *부진의 원인이 답변 LLM이 아니라 전처리 단계*임을 시사합니다.

---

### Table 2. qa_set 별 성적 — vectorrag(40) vs graphrag(40)

| qa_set | LLM | n | Correctness | Faithful | ROUGE-L | 수치 정확도 |
|---|---|---|---|---|---|---|
| vectorrag | gpt-5-mini | 40 | 1.40 | 12.5% | 0.064 | 0.150 |
| vectorrag | kimi-k2.5 | 40 | 1.57 | 7.5% | 0.064 | 0.170 |
| graphrag | gpt-5-mini | 40 | 1.00 | 12.5% | 0.078 | 0.119 |
| graphrag | kimi-k2.5 | 40 | 1.25 | 2.5% | 0.092 | 0.149 |


---

### Table 3. pattern 별 성적 — 영역별 강약 진단

| 영역 | pattern | n | gpt-5-mini C/5 | kimi-k2.5 C/5 | gpt-5-mini Faithful% | kimi-k2.5 Faithful% |
|---|---|---|---|---|---|---|
| ✅ 강점 | negative | 4 | 5.00 | 5.00 | 100.0% | 75.0% |
| ✅ 강점 | limitation | 2 | 1.00 | 4.50 | 50.0% | 50.0% |
| ✅ 강점 | filter_agg | 5 | 1.00 | 1.60 | 0.0% | 0.0% |
| ❌ 약점 | numerical | 23 | 1.00 | 1.30 | 0.0% | 0.0% |
| ❌ 약점 | 1hop | 10 | 1.00 | 1.00 | 10.0% | 0.0% |
| ❌ 약점 | intersection | 8 | 1.00 | 1.00 | 12.5% | 0.0% |
| ❌ 약점 | multi_doc_trend | 10 | 1.00 | 1.00 | 20.0% | 0.0% |
| ❌ 약점 | causal | 5 | 1.00 | 1.00 | 0.0% | 0.0% |
| ❌ 약점 | factual | 9 | 1.00 | 1.00 | 11.1% | 0.0% |
| ❌ 약점 | summary | 4 | 1.00 | 1.00 | 0.0% | 0.0% |


---

### Table 4. Routing Accuracy — pattern 별 (graphrag 40 QA)

> Routing Agent가 질의 유형을 옳게 분류한 비율. 답변 품질과 분리해서 보는 진단 지표.

| pattern | n | gpt-5-mini | kimi-k2.5 |
|---|---|---|---|
| 1hop | 10 | 90.0% | 80.0% |
| multi_doc_trend | 10 | 100.0% | 100.0% |
| intersection | 8 | 100.0% | 100.0% |
| causal | 5 | 100.0% | 100.0% |
| filter_agg | 5 | 0.0% | 60.0% |
| limitation | 2 | 0.0% | 50.0% |
| **전체** | **40** | **80.0%** | **87.5%** |


---

### Table 5. GraphRAG가 빛난 케이스 (Correctness ≥ 4, kimi-k2.5 기준)

| ID | qa_set | pattern | C/5 | Faithful | 질문 |
|---|---|---|---|---|---|
| ds_005 | vectorrag | negative | 5 | ✅ | 이 보고서에서 언급된 한국은행 금통위 일정은? |
| fss_006 | vectorrag | negative | 5 | — | 이 보도자료에서 언급된 회사채 발행 기업의 개별 회사명은? |
| graph_040 | graphrag | limitation | 5 | ✅ | 그래프에서 Company 라벨로 분류된 'AA등급 이상 회사채 발행 비중 73.0%'는 실제 회사명인가? |
| hanwha_002 | vectorrag | numerical | 5 | — | 두산밥칿의 2026년 1분기 예상 영업이익과 OPM은? |
| mirae_4q_006 | vectorrag | negative | 5 | ✅ | 미래에셋증권의 2025년 4분기 배당 지급일은? |
| nonghyup_005 | vectorrag | negative | 5 | ✅ | 이 보고서에 기재된 청산농협의 당기순이익은 얼마인가? |
| fss_002 | vectorrag | numerical | 4 | — | 2025년 10월 CP 및 단기사채 발행액 합계와 전월 대비 증감은? |
| graph_031 | graphrag | filter_agg | 4 | — | 공시(disclosure) 유형 문서에서 다루는 주요 통계 metric은 무엇인가? |
| graph_039 | graphrag | limitation | 4 | — | DS 시황 리포트(2026년 3월)와 한화 두산밥캣 리포트(2026년 3월) 중 어느 것이 더 최신인가? |

> 총 9건 / 80건 = 11.2%. 80% 이상이 *negative* 와 *limitation* 패턴 — 그래프 구조 자체가 답을 만드는 영역.