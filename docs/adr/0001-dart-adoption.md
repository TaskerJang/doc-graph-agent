# ADR-0001: 한국 금융 도메인 분류 체계로 DART 1차 채택, FIBO는 보편 클래스에 한해 차용

## Status

- [ ] Proposed
- [x] **Accepted** (2026-05-02)
- [ ] Deprecated
- [ ] Superseded by #?

## Context

doc-graph-agent의 도메인 온톨로지 설계 시 금융 분류 체계가 필요하다. 검토 후보:

- **FIBO (Financial Industry Business Ontology)** — EDM Council의 글로벌 금융 표준. 주로 미국·유럽 금융 도메인 기준
- **FinDER 8 카테고리** — 영문 10-K 기반 금융 RAG 벤치마크. Company Overview / Financials / Footnotes / Governance / Accounting / Legal / Risk / Shareholder Return
- **DART XBRL 택사노미 + 사업보고서 표준 목차** — 한국 금융감독원 공식 분류 체계. 한국 상장사 공시의 생산 체계

평가 셋(40 QA)이 다음 5종 한국 문서로 구성됨:
- 한화투자증권의 두산밥캣 기업분석 리포트
- DS투자증권의 시황분석 리포트
- 미래에셋증권 자체 IR 실적 보고서 (1Q~4Q)
- 청산농협 사업보고서 (HWP)
- 금융감독원 보도자료 (DOCX)

이 문서들의 **생산 체계 자체가 DART 기반**이며, K-IFRS 맥락·계열회사 구조·영업손익 등 한국 특수 항목은 FIBO와 결이 다름.

## Decision

**한국 금융감독원 DART XBRL 택사노미 + 사업보고서 표준 목차를 1차 분류 체계로 채택한다.** FIBO는 Company / Risk / Outlook 같은 도메인 보편 클래스에 한해 차용. FinDER는 직접 차용하지 않으며, 영문 데이터셋 확장 시 재검토.

근거:
1. 평가 셋이 한국 상장사 사업보고서·증권사 리포트라 해당 문서의 생산 체계(DART)와의 일관성 확보
2. FIBO는 글로벌(미국·유럽) 기준이라 한국 K-IFRS 맥락·계열회사 구조·영업손익 등과 결이 다름
3. DART는 금융감독원의 공식·법적 강제 체계 — "외부 분류 체계 차용"의 정당성 확보
4. 멘토링 권고 (정이태 멘토, 2026-05-02)

## Consequences

**긍정**:
- 한국 평가 셋 도메인과 일관성 있는 라벨 체계 확보
- 발표 자료에서 "왜 이 분류 체계인가"에 대한 명확한 답 (공식 출처)
- DART XBRL 택사노미는 Layer B의 Metric 명칭 표준화에도 활용 가능
- 한국 K-IFRS 기준서 번호 체계와의 자연스러운 매핑 가능

**부정**:
- 글로벌 표준(FIBO) 비중 축소 → 영문 문서로 확장 시 매핑 작업 필요
- DART 택사노미 학습 비용 발생 (IFRS와 다른 한국 특수 항목 파악 필요)
- 다른 한국 금융 RAG 프로젝트와의 직접 비교 시 분류 체계 차이로 비교 어려움

**중립** (트레이드오프·정보성):
- ADR-0002에서 구체 라벨 스키마(옵션 C 2-tier) 결정으로 이어짐
- FIBO 보편 클래스 차용 범위는 W3에서 Layer B 설계 시 재정의 가능
- DART 사업보고서 11개 목차의 직접 차용은 ADR-0002에서 평가 셋 분석 결과를 반영해 보류됨

## Related

- 결정 트리거 이슈: [#9 W2 도메인 온톨로지 설계](https://github.com/TaskerJang/doc-graph-agent/issues/9)
- 결정 박제 코멘트: [#9-issuecomment-4363821681](https://github.com/TaskerJang/doc-graph-agent/issues/9#issuecomment-4363821681)
- 관련 PR: [#30 docs(ontology): Layer A 도메인 온톨로지 설계](https://github.com/TaskerJang/doc-graph-agent/pull/30)
- 후속 ADR: ADR-0002 (Section 스키마 옵션 C 채택)
- 활용 시점:
  - W2 #9 — Layer A Section 라벨 후보 도출
  - W3 #13 — Layer B Entity 라벨 (FIBO 보편 클래스 차용 범위 확정)
  - W3 후반 — DART XBRL Metric 명칭 표준화 적용

## 참고 자료

- DART XBRL 택사노미: http://xbrl.or.kr/
- FIBO Foundation: https://spec.edmcouncil.org/fibo
- FinDER 벤치마크: SEOCHO 강의 자료 (외부 비공개)
- 한국 사업보고서 표준 목차: 금융감독원 공시 양식
