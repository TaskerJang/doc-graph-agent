# ADR-0004: Entity 라벨 체계 + NED 알고리즘 선택

## Status

- [ ] Proposed
- [x] **Accepted** (2026-05-10)
- [ ] Deprecated
- [ ] Superseded by #?

## Context

W3 Entity 추출 (#13) 과 NED (#14) 의 두 결정을 한 곳에 묶는다. 사실상 *"Layer B 가 무엇으로 구성되는가 + 실체 동일성을 어떻게 판정하는가"* 는 하나의 설계 조립.

### 입력 자료

- **ADR-0001**: DART 1차 채택 + FIBO 보편 클래스 차용 — Layer B 라벨 후보 범위 제시
- **ADR-0002**: Layer A Section 스키마 옵션 C — Layer B 는 보편 라벨 + 속성 2-tier 방식 차용 안 함
- **Spike #8** (PR #29): 두산밥캣 1청크 추출 — 4개 라벨 (Company / Metric / Risk / Outlook) 검증, 결함 3건 도출
- **PR #38**: 5개 라벨 적용 프롬프트 v1 검증 — Recommendation 추가
- **PR #39**: NED 알고리즘 3단계 결정 + 6 entities → 4 groups 검증

## Decision

### 결정 1: Layer B Entity 라벨 체계 — 5 EntityType + 4 RelationType

**EntityType** (Pydantic enum, `kg/ontology.py`):

| 라벨 | 설명 | FIBO 상응 |
|---|---|---|
| `Company` | 명시된 회사·조직·계열 | `fibo-be:LegalEntity` |
| `Metric` | 수치·지표 (매출·영업이익·성장률 등) | — (도메인 특수) |
| `Recommendation` | 매수·매도·보유 귶의 투자의견 | — (도메인 특수) |
| `Risk` | 현재 진행 중인 리스크·위협 | `fibo-be:Risk` |
| `Outlook` | 미래 전망·예상 | — (도메인 특수) |

**RelationType** (Pydantic enum):

| 라벨 | 의미 | 예 |
|---|---|---|
| `HAS_METRIC` | Company 가 Metric 을 가짐 | (두산밥캣) -[HAS_METRIC]-> (영업이익 35% 감소) |
| `RECOMMENDED_FOR` | Recommendation 이 Company 에 해당 | (매수 추천) -[RECOMMENDED_FOR]-> (두산밥캣) |
| `FACES_RISK` | Company 가 Risk 에 직면 | (두산밥캣) -[FACES_RISK]-> (북미 수요 둔화) |
| `HAS_OUTLOOK` | Company 가 Outlook 을 가짐 | (두산밥캣) -[HAS_OUTLOOK]-> (Q4 개선 전망) |

**근거**:

1. Spike (4개 라벨) 결과 *"매수 추천"* 같은 Recommendation 함의 정보가 Risk / Outlook / Metric 으로 잘못 흡수됨 → 5번째 라벨 필요성 도출
2. 증권사 리포트 도메인 특성 반영 — "투자의견"이 코어 정보이므로 별도 라벨로 승격
3. ADR-0001 의 FIBO 보편 클래스 차용 원칙과 일치 — Company / Risk 는 FIBO 대응, 나머지는 도메인 특수로 채너널링

### 결정 2: NED 알고리즘 — 임베딩 기반 cosine 그룹화 (3단계)

**파이프라인** (`kg/linking.py`):

```
1. Normalize — 법인 접미사 (㈈, (주), Inc., Co.,Ltd.) / 종목코드 / 공백
2. Embed     — BAAI/bge-m3 (sentence-transformers, L2 normalized)
3. Group     — 같은 type 안 cosine ≥ 0.92 single-link 클러스터링
```

**설계 원칙**:

- **Type 격리**: Company 는 Company 끼리만. type 이 다르면 cosine = 1.0 이어도 별도 그룹 (false merge 방지)
- **Threshold 0.92**: 회사 레포 차용. NED 는 false merge 가 false split 보다 위험 → 보수적으로
- **대표 선정**: 한글 포함 멤버 우선 → 그중 source_span 최장. 한국어 금융 도메인 특성 반영 (외국 회사는 영문 fallback)

**근거**:

1. **bge-m3 선택** — 회사 레포 (`doc-summary-agent`) 와 동일 임베더 → 일관성. 다국어 임베딩 중 한국어 성능 우수. 무료.
2. **0.92 선택** — 회사 레포에서 검증된 숨￡￡￢￡￡.0값. 실측에서 false merge 없음 확인 (`삼성전자` ≠ `삼성SDI`)
3. **대안 명시적 기각**:
   - LLM 기반 NED (Kimi 호출로 동일성 판정) → 비용·latency 부담
   - Alias 사전 (한글-영문 매핑) → 유지보수 부담 + 신규 회사 자동 처리 불가
   - Threshold 완화 (0.92 → 0.85) → false merge 위험 증가
4. **한글 우선 정책 도입** — PR #39 시행착오. v0 (최장 source_span) 은 "Doosan Bobcat" (13자) 가 "두산밥캣㈈" (8자) 보다 길어 영문이 대표가 됨 → 한국어 금융 멘토링 발표·멘토·로그에 어색 → 한글 우선 풌 사용하도록 정책 개정. 외국 회사 (`Apple` / `Apple Inc.` / `AAPL`) 는 영문 fallback 으로 자연 처리.

## Consequences

**긍정**:
- 두산밥캣 1청크 검증 시 5개 라벨 중 4개 활용 (Company / Metric / Risk + 관계 2개) → 라벨 낭비 적음
- NED 단순도 유지 — LLM 호출 없이 임베딩만으로 그룹화 → 비용 0
- 한국어 도메인 특성 반영 — 대표 이름이 자연스럽게 한글
- Type 격리 로 false merge 의 구조적 예방 — `삼성전자` (Company) vs `삼성전자 환율 노출` (Risk) 별도 그룹

**부정**:
- **bge-m3 한영 NED 한계** — 두산밥캣 vs Doosan Bobcat 의 cosine 이 0.92 미달 → 분리됨 (PR #39 검증). false split. 해결은 별도 ADR 후보 (alias 사전 / LLM NED / threshold)
- single-link 클러스터링 은 chain 길이가 길 수록 false merge 위험 → 다수 청크·다수 문서 적재 시 재검토 필요
- bge-m3 최초 다운로드 5–10분 + 메모리 사용 ~3GB — CI 에서는 mock embeddings 로 회피 (PR #39 테스트 구성 참조)
- 5 라벨 고정 — 이후 "회사 계열 (Subsidiary)" 같은 세분화 요구 시 스키마 증가 (Pydantic enum 확장 + 프롬프트 갱신)

**중립** (트레이드오프·정보성):
- 한영 NED 한계는 5/23 발표 자료 *"잘 안 된 것"* 슬라이드 시드로 이용 — 결함이 아니라 점진적 개선 서사의 일부
- W4 Routing (#21) 은 EntityType 을 메타데이터로 사용해 Layer 분기 결정 가능 (예: 텍스트에 Risk / Outlook 언급 → Layer B 우선)
- 해외 레포·운영 환경 확장 시 한국어 우선 정책은 재검토 필요

## Related

- 결정 트리거 이슈: [#42 ADR-0004 트래킹](https://github.com/TaskerJang/doc-graph-agent/issues/42)
- 트래킹 이슈: [#32 ADR 로드맵](https://github.com/TaskerJang/doc-graph-agent/issues/32)
- 상위 ADR: [ADR-0001](./0001-dart-adoption.md), [ADR-0003](./0003-llm-kimi.md)
- 검증 PR: [#38 Entity 추출 v1](https://github.com/TaskerJang/doc-graph-agent/pull/38), [#39 NED + Dedup](https://github.com/TaskerJang/doc-graph-agent/pull/39)
- 관련 이슈: [#9 (closed) Layer B 설계](https://github.com/TaskerJang/doc-graph-agent/issues/9), [#13 (closed) Entity 추출](https://github.com/TaskerJang/doc-graph-agent/issues/13), [#14 (closed) NED + Dedup](https://github.com/TaskerJang/doc-graph-agent/issues/14)
- 활용 시점:
  - W3 #15 적재 — 5 EntityType 이 Neo4j 라벨로 적용 (PR #40)
  - W4 #21 Routing — EntityType 메타데이터 활용

## 참고 자료

- bge-m3 모델: https://huggingface.co/BAAI/bge-m3
- sentence-transformers: https://www.sbert.net/
- Pydantic enum: https://docs.pydantic.dev/latest/api/standard_library_types/#enum
- 회사 레포 NED 패턴 참고: `doc-summary-agent` (은행 레포 서는 소스 코드 공개 명시 잘은 적 없으나, 추출용 임베더는 공유)
