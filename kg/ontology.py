"""Layer B 도메인 온톨로지 — Entity·Relation 스키마 (Pydantic).

5개 Entity 타입 + 4개 Relation 타입의 핵심 어휘를 정의한다.
LLM 추출기(`kg/extractor.py`)와 NED(`kg/linking.py`), 적재기(`kg/builder.py`)
모두 이 모듈의 모델을 공통 인터페이스로 사용한다.

설계 원칙 (#9 온톨로지, #13 추출):
- **Layer B 책임에만 집중**: 문서 구조(Section/Chunk)는 Layer A 의 ingestion/
  ontology 가 다룬다. 본 모듈은 의미적 노드(Company 등)와 그들 사이 관계만.
- **원문 추적성**: 모든 Entity 는 `source_span` (원문 인용) 을 들고 있어야
  Spike (#8) 시행착오 #3 에서 확인된 "수치 보존 원칙" 을 만족한다.
- **청크 로컬 ID**: LLM 응답 내에서만 의미 있는 `local_id` 로 청크 안 관계를
  연결한다. 전역 ID 는 #14 NED (Named Entity Disambiguation) 단계에서 부여.

회사 레포 비교 (`doc-summary-agent/summarizer/llm.py` SectionSummary):
회사 레포는 단일 Pydantic 모델 1개로 끝났는데, 본 모듈은 Entity/Relation 분리.
이유: GraphRAG 는 노드뿐 아니라 관계가 1급 시민이라 동등하게 모델링.

관련 이슈: #9, #13.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ── Entity 타입 ────────────────────────────────────────────
class EntityType(str, Enum):
    """Layer B Entity 라벨.

    5개로 한정한 이유:
    - 금융 보고서·리서치 노트의 정보 단위가 대부분 이 5개로 환원됨
    - 너무 많으면 LLM 라벨 일관성 저하 (#8 Spike 에서 4개도 실수 있었음)
    - 후속 멘토링 주차에서 부족하면 확장 (현재는 LPG 모델의 :Label 로 대응)
    """

    COMPANY        = "Company"        # 기업·종목 (예: "삼성전자", "두산밥캣")
    METRIC         = "Metric"         # 재무·실적 지표 (예: "영업이익 32조", "EPS 1,234원")
    RECOMMENDATION = "Recommendation" # 투자의견·목표가 (예: "매수 의견", "목표가 90,000원")
    RISK           = "Risk"           # 리스크·하방 요인 (예: "환율 변동성", "수출 둔화")
    OUTLOOK        = "Outlook"        # 전망·예상 (예: "2026년 두 자릿수 성장 전망")


# ── Relation 타입 ─────────────────────────────────────────
class RelationType(str, Enum):
    """Layer B Relation 라벨 (방향성 명시).

    Spike (#8) 에서 라벨만 추출하고 관계는 미검증이었음. 본 작업에서 정식화.
    Cypher 적재 시 화살표 방향 = enum 주석의 source → target.
    """

    HAS_METRIC      = "HAS_METRIC"       # Company → Metric
    RECOMMENDED_FOR = "RECOMMENDED_FOR"  # Recommendation → Company
    FACES_RISK      = "FACES_RISK"       # Company → Risk
    HAS_OUTLOOK     = "HAS_OUTLOOK"      # Company → Outlook


# ── Pydantic 모델 ─────────────────────────────────────────
class ExtractedEntity(BaseModel):
    """LLM 이 추출한 Entity 1건.

    `local_id` 는 청크 안에서만 유일. 청크 간 동일성 판단은 #14 NED 의 책임.
    """

    local_id:    str        = Field(..., description="청크 내 임시 ID. 예: 'ent_001'")
    type:        EntityType = Field(..., description="5개 EntityType 중 하나")
    canonical:   str        = Field(..., description="정규화된 표면형 이름")
    source_span: str        = Field(
        ...,
        description="원문 그대로의 인용. 수치는 변환·반올림 금지 (#8 시행착오 박제).",
    )
    section:     str | None = Field(
        default=None,
        description="원문 섹션명 (있으면). Layer A 의 Section 노드와 후속 연결용.",
    )


class ExtractedRelation(BaseModel):
    """LLM 이 추출한 Entity 간 관계 1건.

    source/target 은 같은 청크 내 ExtractedEntity 의 `local_id` 를 참조.
    """

    source:   str          = Field(..., description="source Entity 의 local_id")
    type:     RelationType = Field(..., description="4개 RelationType 중 하나")
    target:   str          = Field(..., description="target Entity 의 local_id")
    evidence: str          = Field(
        ...,
        description="관계의 근거가 된 원문 인용 (Faithfulness 추적용).",
    )


class ExtractionResult(BaseModel):
    """단일 청크에 대한 LLM 추출 결과.

    `kg/extractor.py` 의 청크별 호출이 반환하는 단위. NED(#14) 의 입력.
    """

    entities:  list[ExtractedEntity]   = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
