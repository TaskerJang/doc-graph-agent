# 2026-05-17 — W4 점검 + 남은 일정 박제 (#22)

> Status: **W4 점검 완료, 시나리오 A 정상 진행 결정 (빠듯해도 5행 표까지 완주).**
> 5/16 → 5/17 → 5/18 → 5/19 → 5/20 → 5/21 → 5/22 → 5/23 발표까지 일정 박제.

## 🎯 #22 W4 점검 결정 — 시나리오 A 정상 진행

### 결정 근거 (5/17 PR #48 머지 직전)

1. **Layer A 완료** — PR #48 (Text2Cypher 8/8 PASS)
2. **이미 발표 핵심 메시지 확보**:
   - Entity 라벨 품질 challenge (5/16 + 5/17 Q5 정량 확정)
   - VectorRAG ↔ GraphRAG 보완 관계 (Q4 0 rows 증거)
3. **W4/W5 일정 빠듯하지만 완주 가능**

### 시나리오 A 정상 범위 + 일정

```
✅ Layer A (Text2Cypher) — PR #48 (5/17 머지 대기)
🔴 5/17 (일) Layer B (Local Retriever) — #19
🔴 5/18 (월) Layer C (Community stub) — #20
🔴 5/18 (월) Routing Agent (rule-based) — #21
🔴 5/19 (화) Hybrid Score Fusion (옵션 A) — #23
🔴 5/20 (수) LLM 어댑터 (외부 레포) — #25, #3, #35
🔴 5/21~22 (목~금) 5행 표 측정 — #26, #1 ablation
🔴 5/22 (금) 발표 자료 — #27
⭐ 5/23 (토) 발표일 — #28
```

### #4 Hybrid 설계 결정 (close)

**옵션 A (Score Fusion) 채택** — 시나리오 A 정합 + W5 일정 적합.
옵션 B (Routing Hybrid) 는 future work (#46 OpenAI 마이그 후 별도 작업).

## 📅 일정 상세 박제 (5/17 ~ 5/23)

### 5/17 (일) — Layer B Local Retriever
- 오전: PR #48 머지 + 이슈 #18 close
- 오후 (3~4시간): `retrieval/local_retriever.py` 구현
- 저녁: 평가 셋 L1~L5 정성 검증 (#19 평가 셋 박제)

### 5/18 (월) — Layer C + Routing
- 저녁 19~21시: `retrieval/community.py` (#20)
- 저녁 21~22시: 글로벌 질의 정성 검증 (G1~G4 박제)
- 늦은 밤 22~23시: `agent/router.py` (#21)
- 늦은 밤 23~24시: 14 케이스 라우팅 정확도 측정

### 5/19 (화) — Hybrid Score Fusion
- 저녁 19~21시: `agent/hybrid.py` 구현 (#23)
- 저녁 21~22시: 10 QA 정성 검증

### 5/20 (수) — LLM 어댑터 + 외부 측정
- 외부 레포 작업 (doc-summary-agent#127, #25)
- VectorRAG Before 700/200 재측정 (Kimi + GPT-5.2, #35)
- VectorRAG Full Kimi/GPT-5.2 측정 (#3)
- 총 3~4시간 예상

### 5/21 (목) — 5행 표 자동화 (#26)
- 저녁 19~21시: `eval/runner.py` + `eval/metrics.py`
- 저녁 21~23시: 측정 시작 (백그라운드)

### 5/22 (금) 새벽 — 측정 완료 + 발표 자료
- 새벽 ~03시: 5행 표 결과 검증
- 저녁 19~24시: 발표 슬라이드 작성 (#27)

### 5/23 (토) — 발표일 ⭐
- 오전: 슬라이드 최종 검토 + 시연 환경 점검 + 리허설
- 오후: 발표 + 질의응답
- 저녁: 회고 + 글 [회고] 발행

## 🗂️ 이슈 정리 결과 (5/16~17 박제)

### Close 처리 (결정 박제 후)
- ✅ **#4** Hybrid 설계 정체 — 옵션 A (Score Fusion) 채택

### 진행 시점 박제 (코멘트 추가)
- #19 Layer B (5/17 진행) — 평가 셋 L1~L5 박제 예정
- #20 Layer C (5/18 진행) — 평가 셋 G1~G4 박제 예정
- #21 Routing Agent (5/18 진행) — mode 토글 구조
- #22 W4 점검 (결정 박제, 진행 후 close)
- #23 W5 Hybrid (5/19 진행) — Score Fusion 범위 확정
- #25 LLM 어댑터 (5/20 진행, 외부 레포)
- #26 W5 5행 표 (5/21~22 진행) — 6행 측정 범위 (5 + 보너스 ablation)
- #27 발표 자료 (5/22 진행) — 19장 슬라이드 (12 박제 + 7 신규)
- #1 LLM 통일 (5/22 ablation 측정 시 close)
- #3 시나리오 B (5/20 #25 와 묶음)
- #35 Before 700/200 (5/20 #25 와 묶음)
- #32 ADR 트래킹 (0005/0006/0007 발행 일정 박제)

### Future Work (post-mentoring)
- #37 OCR 마커 분리 — 5/24+ (시간 있으면)
- #46 OpenAI 마이그 — 5/24~26 연휴
- #47 6/1 회사 발표 — 5/27~31

### Open 유지 (참고용)
- #28 ⭐ 5/23 발표일 — 발표 후 close
- #32 ADR 트래킹 — 0005~0007 발행 후 close

## 📊 진척률

```
W1 (4/27~5/1)  ████████████ 100% (PR #29~31 완료)
W2 (5/2~5/8)   ████████████ 100% (PR #32~36 완료)
W3 (5/9~5/15)  ████████████ 100% (PR #37~45 완료)
W4 (5/16~5/22) ███░░░░░░░░░  25% (PR #48 = Layer A 완료)
W5 (5/19~5/22) ░░░░░░░░░░░░   0%
```

→ W4 완료까지 **2일** (5/17 일 + 5/18 월), W5 완료까지 **4일** (5/19~22), 발표 D-day **6일** 남음.

## 🎤 발표 자료 박제 현황 (5/22 작업 전)

### 이미 박제 완료 (5/16 + 5/17, 12장)
1. 문제 정의 (VectorRAG Completeness 1.25/5)
2. SemanticChunker 발견 (820자/31초)
3. LangChain sequential 한계 분석
4. trade-off 표
5. fallback 구현 (USE_SIMPLE_CHUNKER)
6. 운영 데이터 (8/8 100%, 76분)
7. 포맷 다양성 (PDF + HWP + DOCX)
8. production 의존성 (LibreOffice)
9. 그래프 통계 (610 / 2,451 / 1,189)
10. **⭐⭐⭐ Entity 라벨 품질 challenge** (Q5 정량)
11. **⭐ VectorRAG ↔ GraphRAG 보완 관계** (Q4 0 rows)
12. **Text2Cypher 데모** (Q2 5.7초)

### W4~W5 완료 시 추가 박제 (7장)
13. Layer B Local Retriever 정성 검증 (#19)
14. Layer C Community + 글로벌 질의 (#20)
15. Routing Agent 정확도 (#21)
16. **5행 표 정량 비교** ⭐⭐⭐ (#26)
17. LLM ablation (#1 길 4 보너스)
18. Future Work — 옵션 B Routing Hybrid (#4 미채택)
19. Lessons — 시행착오 박제

→ **총 19장** (12 박제 + 7 신규).

## 🛡️ 위험 대응 (#26 측정 실패 시 fallback)

| 위험 | 대응 |
|------|------|
| #19 Local Retriever 실패 | Layer A (Text2Cypher) 만으로 진행 |
| #20 Community 실패 | 시나리오 A 축소판, future work |
| #21 Routing 실패 | Layer A 직접 호출, 라우팅 future work |
| #23 Hybrid 실패 | 4행 표 (Vector + GraphRAG) 만 |
| #1 ablation 실패 | "future work" 표시 |
| **최악 fallback**: Layer A + 8/8 PASS + 발표 자료 12장 → **이미 충분히 강력** |

## 관련

- PR #48 (Text2Cypher 8/8 PASS, 머지 대기)
- #22 (W4 점검 결정 박제)
- #4 (Hybrid 설계, close 예정)
- #32 (ADR 트래킹, 0005~0007 발행 일정)
- #46, #47 (post-mentoring)
