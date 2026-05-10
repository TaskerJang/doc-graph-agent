# ADR-0003: LLM 선택 — Kimi (Moonshot k2.5) 채택

## Status

- [ ] Proposed
- [x] **Accepted** (2026-05-10)
- [ ] Deprecated
- [ ] Superseded by #?

## Context

doc-graph-agent 의 모든 LLM 호출을 책임질 모델을 결정해야 한다. 사용 지점:

- W3 Entity 추출 (`kg/extractor.py`) — 청크당 1회, 문서당 N회
- W4 Text2Cypher (`retrieval/text2cypher.py`) — 질의당 1회
- W4 답변 생성 (Layer B/C retrieval) — 질의당 1–2회
- W4 Routing (선택 적용) — 질의당 1회

마일스톤 #16 통과 후 8문서 × 40 QA 관점에서 운영 비용·latency 다 중요.

### 후보 매트릭스

| LLM | 비용 (입력) | 한국어 | OpenAI SDK 호환 | Context-caching | 채널 |
|---|---|---|---|---|---|
| **Kimi (Moonshot k2.5)** | 저렴 | 우수 | ✅ | 우수 | 멘토링 활동비 |
| OpenAI GPT-5.2 | 고 | 우수 | ✅ 기본 | 최근 추가 | 개인 부담 |
| DeepSeek | 저렴 | 미검증 | ✅ | 우수 | 멘토링 권고 |
| Claude Sonnet 4.6 | 중 | 우수 | API 다름 | 제한적 | 개인 부담 |

### Spike (#8) 검증 결과 (5/9–5/10)

- OpenAI SDK `base_url=https://api.moonshot.ai/v1` 경로로 Kimi 호출 성공 (시행착오 1건 박제 — `.cn` 이 기본 텍스트에 있으나 글로벌 엔드포인트는 `.ai`)
- 두산밥캣 1청크 Entity 추출 성공 (Spike v0)
- v1 프롬프트 (PR #38) 로 v0 결함 3건 개선 확인:
  - Metric 통합·분리 교정
  - Risk 분류 정확
  - Relations 추출

## Decision

**Kimi (Moonshot k2.5) 를 채택한다.** 멘토링 종료 (5/23) 까지 변경 없으며, 모델 호출은 `agent/llm_client.py` thin wrapper 를 통해 단일 진입점으로 적재한다. 환경변수 (`KIMI_API_KEY` / `KIMI_BASE_URL` / `KIMI_MODEL`) 로 보적.

근거:

1. **멘토링 활동비 충당 권고** — 멘토 정이태 (Hardy) 의 명시적 안내. doc-graph-agent 는 멘토링 결과물이므로 이 의도에 따르는 것이 자연스럽다.
2. **운영 비용 필요** — 8문서 × 40 QA × 재측정 공수 (W5 5행 표). GPT-5.2 는 개인 계정에 큰 부담.
3. **Spike 검증 완료** — OpenAI SDK 호환 확인 + 한국어 Entity 추출 품질 검증 끝.
4. **VectorRAG vs GraphRAG 비교 때 LLM 차이 의 수단은 별도 결정됨** — 이슈 #1 "LLM 통일 전략" 의 길 4 (차이 인정 + 보너스 ablation) 채택. 즉, *Kimi 채택 자체는 비교 표의 공정성을 해치지 않는다*.

### 구체 설정

```
KIMI_API_KEY    = sk-... (멘토 배부 키)
KIMI_BASE_URL   = https://api.moonshot.ai/v1   # .cn 이 아닌 글로벌
KIMI_MODEL      = moonshot-v1-8k                # 추출·답변용 기본
```

운영 파라미터 (참고 — 고정 결정 아님):
- Temperature: 0.2 (Entity 추출 결정적) → 0.7 (답변 생성)
- Max tokens: 1500 (청크당 추출) / 2000 (답변)
- Concurrency: Semaphore(8) — Kimi 글로벌 rate limit 여유

## Consequences

**긍정**:
- 멘토링 의도 부합 — "와 이 LLM을 쓰는가" 에 대한 부담 없이 답변
- 운영 비용 절감 — GPT-5.2 대비 대폭 저렴
- OpenAI SDK 호환으로 이후 키 교체·모델 교체 추상화가 쉬움 (모델 이름 / base_url / API 키 3개의 환경변수만 교체)
- 한국어 결과 품질 — 두산밥캣 검증에서 GPT 대비 손색 없음

**부정**:
- 회사 레포 (`doc-summary-agent`) 와 LLM 이 다름 → VectorRAG vs GraphRAG 직접 비교 시 "LLM 차이 vs Retrieval 차이" 분리 필요 → 이슈 #1 길 4 (보너스 ablation) 으로 의존적 해결
- Kimi rate limit · 장애 시 멘토링 일정 안정성에 직접 영향 → 폴백 계획 필요 (소규모 OpenAI 키 우회로)
- DeepSeek · Claude 대비 성능 차이는 별도 마이그레이션 시 재고려

**중립** (트레이드오프·정보성):
- ADR-0004 (Entity 라벨 + NED 알고리즘) 결정이 본 ADR 의 LLM 권장 파라미터 (Temp / Concurrency) 를 근거로 삼음
- W5 평가 (#26 5행 표) 의 "Graph + GPT-5.2" ablation 이 LLM 차이 분리용 참고치 제공
- W3 Entity 추출 프롬프트는 Kimi 솤 attention 특성 (번호 헤더 / 마크다운 표 / 구체 태그) 을 반영해 설계됨 → GPT 으로 교체 시 프롬프트 재대비 필요

## Related

- 결정 트리거 이슈: [#41 ADR-0003 트래킹](https://github.com/TaskerJang/doc-graph-agent/issues/41)
- 트래킹 이슈: [#32 ADR 로드맵](https://github.com/TaskerJang/doc-graph-agent/issues/32)
- 검증 PR: [#29 Spike #8 (머지됨)](https://github.com/TaskerJang/doc-graph-agent/pull/29), [#38 Entity 추출 v1](https://github.com/TaskerJang/doc-graph-agent/pull/38)
- 관련 이슈: [#1 LLM 통일 전략 (길 4 보너스 ablation)](https://github.com/TaskerJang/doc-graph-agent/issues/1)
- 활용 시점:
  - W3 #13 Entity 추출 — Kimi 적용 끝 (PR #38)
  - W4 #18 Text2Cypher — Kimi 적용 예정
  - W4 #19/#20 답변 생성 — Kimi 적용 예정
  - W5 #26 5행 표 (Graph + Kimi 행) + ablation (Graph + GPT-5.2)

## 참고 자료

- Moonshot AI: https://platform.moonshot.ai/
- OpenAI SDK: https://github.com/openai/openai-python
- Spike #8 시행착오 3건 (PR #29 코멘트): SSL self-signed cert / Kimi base_url `.cn` → `.ai` / f-string + .format() 이중 처리
