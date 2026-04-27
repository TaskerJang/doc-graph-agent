# agent/

**책임**: Routing Agent + Debate Pool + Tool Binding. Layer 분기와 합성을 책임진다.

**출처**: 신규.

## 모듈 (예정)

- `router.py` — 질문 유형별 Layer 분기
- `debate_pool.py` — 다중 Agent 토론 + Supervisor 합성 (W4 후반)
- `tools.py` — OpenAI Agents SDK Tool Binding 패턴

## Routing Policy 초안

| 질문 패턴 | 라우팅 대상 |
|---|---|
| 전체 흐름·요약·트렌드 | Layer C (Community Summary) |
| 특정 엔티티·관계·비교 | Layer B (Local Retriever) |
| 출처 인용·원문 발췌·표 데이터 | Layer A (Text2Cypher) |

구체 분기 기준은 ADR-0003에서 확정 (W4).

## 참고

- 책: *Knowledge Graphs and LLMs in Action* Ch 15 (LangGraph QA Agent)
- 멘토링 자료: SEOCHO Agent (AgentFactory, Shared Memory, Debate)
