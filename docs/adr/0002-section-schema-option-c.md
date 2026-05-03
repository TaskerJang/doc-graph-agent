# ADR-0002: Layer A Section 스키마는 보편 라벨 + doc_type/original_section 속성 (옵션 C)

## Status

- [ ] Proposed
- [x] **Accepted** (2026-05-02)
- [ ] Deprecated
- [ ] Superseded by #?

## Context

[ADR-0001](./0001-dart-adoption.md)에서 DART 1차 채택을 결정한 직후, Layer A Section 스키마 구체 설계를 위해 평가 셋 40 QA를 분석한 결과 다음이 드러남:

- DART 사업보고서 표준 목차 11개를 직접 라벨로 사용하기 어려움
- 평가 셋 문서 분포:
  - 증권사 기업분석 리포트(한화-두산밥캣): 6 QA (15.0%)
  - 증권사 시황 리포트(DS): 5 QA (12.5%)
  - IR 실적 보고서(미래에셋 1Q~4Q): 18 QA (45.0%)
  - 사업보고서(농협 HWP): 5 QA (12.5%)
  - 보도자료(금감원 DOCX): 6 QA (15.0%)
- DART 사업보고서 양식이 직접 적용되는 비중은 12.5%(농협 1건)뿐

**즉, 단일 분류 체계로는 5종 문서를 일관 적용 불가.**

세 옵션 검토:

| 옵션 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A | 문서 타입별 5개 스키마 분기 | 정확한 매핑 | W3 LLM 추출 프롬프트 5배 복잡 |
| B | 보편 라벨만 (Overview/Performance 등) | 단일 스키마 | 원본 섹션명 정보 손실 |
| C | 보편 라벨 + doc_type/original_section 속성 | 그래프 단순 + 정보 보존 + 라우터 분기 | 약간의 코드 복잡도 |

## Decision

**옵션 C — 보편 라벨 + doc_type/original_section 2-tier 스키마를 채택한다.**

Section 노드 정의:

```cypher
(:Section {
  label: enum,                   // 보편 8개 라벨 중 하나
  doc_type: enum,                // "report" | "ir" | "disclosure" | "filing"
  original_section: string,      // 원본 섹션명 그대로 보존
  ...
})
```

**보편 라벨 8개**:
1. `Overview` — 표지·요약·Key Highlights
2. `Performance` — 실적·재무 수치
3. `Outlook` — 전망·가이던스·목표
4. `Risk` — 리스크 요인·불확실성
5. `Recommendation` — 투자의견·목표주가 (증권사 리포트 전용)
6. `BusinessSegment` — 사업부문별 분석
7. `Statistics` — 통계·집계 데이터
8. `Disclaimer` — 면책·법적 고지 (검색 제외 대상)

**doc_type 4종**:
- `report` — 증권사·연구기관 리포트
- `ir` — 기업 자체 IR 자료
- `disclosure` — 정부·감독기관 공시·보도자료
- `filing` — 법정 공시 사업보고서

근거:
1. 옵션 A는 W3 Entity 추출 프롬프트가 5배 복잡해져 LLM 분류 정확도 저하 위험
2. 옵션 B는 "1Q 2025 Key Highlights" 같은 원본 섹션명 정보 손실 → 발표 자료에서 원본 추적 약화
3. 옵션 C는 LLM은 보편 라벨로만 분류하면 되고(단순), 라우터는 doc_type으로 문서 타입 분기 가능, 발표 자료는 original_section으로 원본 추적 가능
4. 평가 셋 5종 문서에서 1개씩 매핑 검증 모두 통과 (PR #30 §5)

## Consequences

**긍정**:
- LLM 분류 프롬프트 단순 (8개 enum)
- 원본 섹션명 보존 → 발표 자료의 원본 추적 가능
- 라우터에서 doc_type 분기 가능 → 문서 타입별 다른 retrieval 전략 적용 여지
- 5종 문서 통합 처리 가능 (HWP "표지", PDF "Key Highlights", DOCX "개황"이 모두 `Overview`로 통합됨)
- 기존 chunker.py의 `SKIP_SECTION_KEYWORDS` 휴리스틱이 `Disclaimer` 라벨로 흡수 → 온톨로지 안에 명시화

**부정**:
- LLM 분류 시 모호 케이스 발생 가능 (예: "리스크 관리 전략" → `Risk`? `Outlook`?)
- 단일 라벨로 강제 → 본질적으로 다중 의미를 가진 섹션의 정보 손실 가능성
- 라벨이 늘어나면 enum 관리 부담 증가

**중립** (트레이드오프·정보성):
- 다중 라벨 허용 여부는 W3 #13에서 LLM 추출 결과 본 후 재결정
- `Risk` 라벨은 평가 셋에 없으나 사업보고서 X장(투자자 보호 사항)에서 활용 예상
- 8개 라벨이 충분한지는 W3 진행하며 검증 (#13 결과로 보강)
- DART 사업보고서 11개 목차 직접 차용은 보류 — DART의 활용은 Layer B Metric 표준화로 이관 (ADR-0001과 일치)

## Related

- 결정 트리거 이슈: [#9 W2 도메인 온톨로지 설계](https://github.com/TaskerJang/doc-graph-agent/issues/9)
- 결정 박제 코멘트: [#9-issuecomment-4363833813](https://github.com/TaskerJang/doc-graph-agent/issues/9#issuecomment-4363833813)
- 관련 PR: [#30 docs(ontology): Layer A 도메인 온톨로지 설계](https://github.com/TaskerJang/doc-graph-agent/pull/30)
- 선행 ADR: ADR-0001 (DART 채택)
- 후속 검토 항목 (W3에서):
  - Section 다중 라벨 허용 여부 (#13)
  - `Document.analyst_name` 등 표지 메타 필드 추가 (#13)
  - Section 계층 깊이 제한 (현재 3depth 가정)
  - `Chunk -[:NEXT_SECTION]-> Chunk` 도입 여부 (W3 후반)

## 검증 결과

평가 셋 5종 문서 1개씩 Cypher 쿼리로 매핑 검증 통과 (PR #30 §5):

| QA | 문서 종류 | 매핑 결과 |
|---|---|---|
| `hanwha_001` | 증권사 기업분석 리포트 | ✅ Document → Section(:Recommendation) → Chunk |
| `ds_001` | 증권사 시황 리포트 | ✅ Document 메타 또는 Section(:Statistics) |
| `mirae_4q_001` | IR 실적 보고서 | ✅ Document → Section(:Overview) → Chunk/Table |
| `nonghyup_001` | 사업보고서 (HWP) | ✅ Document → Section(:Overview) → Chunk |
| `fss_001` | 금감원 보도자료 | ✅ Document → Section(:Overview) → Chunk/Table |
