# CLAUDE.md

Claude Code가 이 레포에서 작업할 때 참고할 컨텍스트. `AGENTS.md`와 동일한 내용을 둔다 (도구별 분리 컨벤션 준수).

자세한 내용은 [AGENTS.md](./AGENTS.md) 참고.

## 핵심 요약

- **목표**: VectorRAG 기반 `doc-summary-agent`를 SEOCHO Layer A/B/C 구조의 GraphRAG로 재구성
- **Layer 분리**: A(문서 구조)/B(엔티티 관계)/C(커뮤니티/토픽)는 책임이 다르다. 섞지 마라.
- **평가 동일성**: `eval/dataset/qa_pairs.json` (40개)은 Before/After 비교 기준선이다. 수정 금지.
- **시행착오 박제**: 코드 주석·commit message에 이슈 번호와 "왜 그러는지"를 남긴다.

## 작업 전 확인

1. 어느 Layer의 작업인가?
2. 기존 레포에서 포팅인가, 신규 설계인가?
3. 관련 이슈가 있는가?
4. 평가 셋에 영향을 주는가?
