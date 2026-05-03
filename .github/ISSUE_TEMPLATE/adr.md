---
name: ADR (Architecture Decision Record)
about: 프로젝트의 중요 의사결정을 박제하기 위한 문서. 결정의 근거·결과·트레이드오프를 명시화한다.
title: '[ADR-NNNN] '
labels: ['adr', 'adr:accepted']
assignees: ''
---

> Michael Nygard 형식 기반. 한 페이지를 넘지 않게 작성한다.
> 정본 파일: `docs/adr/NNNN-slug.md` (이슈 클로즈 시 PR 머지로 박제)

## Status

현재 상태에 `[x]` 표시. 결정 변경 시 새 ADR 발행 후 본 ADR을 `Superseded` 처리.

- [ ] Proposed (제안 상태, 아직 결정 전)
- [ ] Accepted (채택, 현재 유효)
- [ ] Deprecated (사용 중단, 단 대체안 없음)
- [ ] Superseded by #? (대체 ADR로 승계됨)

## Context

어떤 상황이었나? 왜 결정이 필요했나? 어떤 후보들이 있었나?

- 배경 사실 1
- 배경 사실 2
- 검토한 옵션:
  - 옵션 A: ...
  - 옵션 B: ...
  - 옵션 C: ...

## Decision

무엇을 결정했나? **명확한 단일 문장으로 시작.**

근거:
1. 근거 1
2. 근거 2
3. (선택) 멘토·외부 권고

## Consequences

이 결정의 결과를 긍정·부정·중립으로 분리.

**긍정**:
-

**부정**:
-

**중립** (정보성, trade-off):
-

## Related

- 관련 이슈: #?
- 관련 PR: #?
- 후속 ADR: ADR-NNNN (작성 예정)
- 정본 파일: `docs/adr/NNNN-slug.md`
