# Architecture Decision Records (ADRs)

본 디렉토리는 doc-graph-agent 프로젝트의 주요 아키텍처 결정을 박제한 문서들을 보관한다.

## 형식

[Michael Nygard 형식](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)을 기반으로 한다.

각 ADR은 다음 4개 섹션으로 구성된다:
- **Status**: Proposed / Accepted / Deprecated / Superseded
- **Context**: 결정이 필요했던 배경과 검토 옵션
- **Decision**: 무엇을 결정했고 왜
- **Consequences**: 긍정·부정·중립의 결과

## 운영 방식

각 ADR은 **이슈 + 파일 이중 관리** 구조를 따른다.

1. **이슈** — `.github/ISSUE_TEMPLATE/adr.md` 템플릿으로 생성. 라벨 `adr`, `adr:accepted`. 토론·이력·외부 참조용.
2. **파일** — `docs/adr/NNNN-slug.md`. 정본(source of truth). 깃 이력에 박힘.
3. **인덱스** — 본 README. 모든 ADR 목록 + 상태.

새 결정이 기존 결정을 대체할 때:
- 기존 ADR Status를 `Superseded by ADR-XXXX (#issue)`로 변경
- 새 ADR 작성

## 인덱스

| #    | Title                                              | Status   | Date       | Issue |
| ---- | -------------------------------------------------- | -------- | ---------- | ----- |
| 0001 | DART 채택, FIBO 보편 클래스 차용                  | Accepted | 2026-05-02 | #9    |
| 0002 | Section 스키마 옵션 C — 보편 라벨 + 속성 2-tier   | Accepted | 2026-05-02 | #9    |
| 0003 | LLM 선택 — Kimi (Moonshot k2.5) 채택                | Accepted | 2026-05-10 | #41   |
| 0004 | Entity 라벨 체계 + NED 알고리즘 선택                  | Accepted | 2026-05-10 | #42   |

## 향후 작성 예정

| 예정 # | 주제                                  | 시점     |
| ----- | ------------------------------------- | -------- |
| 0005  | Community Detection 알고리즘 선택      | W4       |
| 0006  | 라우팅 정책 (시나리오 A vs B)         | W4 점검일 |
| 0007  | Hybrid Score Fusion 가중치             | W5       |

## 참고

- 형식 출처: https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- 한국어 해설: https://engineering.linecorp.com/ko/blog/architecture-decision-records (참고 자료)
