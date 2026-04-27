# observability/

**책임**: Opik 트레이싱 + Span 정의 + 평가 연동.

**출처**: 신규 (W5 집중).

## 모듈 (예정)

- `tracing.py` — `@track` 데코레이터 wrapper, span 메타 표준화
- `evaluators.py` — 라우팅 정확도, 응답 품질, 비용 추적
- `experiments.py` — A/B 비교용 evaluation 프레임워크

## 환경 변수

```
OPIK_URL=...
OPIK_WORKSPACE=...
OPIK_PROJECT_NAME=doc-graph-agent
OPIK_API_KEY=...
```

## Span 설계 원칙

- 함수 레벨 span은 `@track`으로 감싼다
- 라우팅 결정·LLM 호출·Cypher 실행은 별도 span으로 가시화
- Layer 식별 메타를 모든 span에 attach (`layer=A|B|C`)

## 참고

- Opik 공식 문서: https://www.comet.com/docs/opik/
- 책에 별도 Observability 챕터 없음 — Opik 문서를 메인으로 함
