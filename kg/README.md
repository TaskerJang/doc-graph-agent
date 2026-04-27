# kg/

**책임**: Knowledge Graph 구축 — Entity 추출, Linking, Dedup, Neo4j/DozerDB 적재.

**출처**: 신규 (멘토링 핵심 작업 영역).

## 모듈 (예정)

- `ontology.py` — 도메인 스키마 정의 (Pydantic 모델)
- `extractor.py` — LLM 기반 Entity·Relation 추출
- `linking.py` — Named Entity Disambiguation (NED) + Cosine similarity dedup
- `builder.py` — Cypher MERGE 기반 그래프 적재
- `community.py` — Layer C용 community detection (Leiden, Louvain)

## 참고

- 책: *Knowledge Graphs and LLMs in Action* Ch 5~8 (Entity Extraction, NED)
- FinDER 데이터셋 패턴 분석 (W3)
- 기존 레포 `chunker.py`의 `_METRIC_KEYWORDS`를 ontology의 출발 어휘로 활용
