"""kg/extractor.py 단위 테스트.

LLM 은 mock 해서 네트워크 없이 돌아가게 함. CI 친화.
DoD (#13):
- 빈 청크 graceful (KeyError 없이 빈 결과)
- 알 수 없는 라벨 drop (graceful)
- 두산밥캣 샘플 (Spike v0 재용) 파이프라인 end-to-end
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from kg.extractor import extract
from kg.ontology import EntityType, RelationType


# ── 공통 fixture ────────────────────────────────────────
DOOSAN_TEXT = (
    "두산밥캣은 2024년 3분기 영업이익이 전년 동기 대비 35% 감소했다고 공시했다. "
    "북미 시장의 고금리 장기화로 건설장비 수요가 둔화된 것이 주된 원인이다."
)

# v1 프롬프트가 기대하는 이상적 응답 (entity_extract_v1.md 의 4.3 원형).
DOOSAN_IDEAL_RESPONSE = json.dumps(
    {
        "entities": [
            {
                "local_id": "ent_001",
                "type": "Company",
                "canonical": "두산밥캣",
                "source_span": "두산밥캣",
                "section": "3분기 실적",
            },
            {
                "local_id": "ent_002",
                "type": "Metric",
                "canonical": "영업이익 전년 동기 대비 35% 감소 (2024Q3)",
                "source_span": "2024년 3분기 영업이익이 전년 동기 대비 35% 감소",
                "section": "3분기 실적",
            },
            {
                "local_id": "ent_003",
                "type": "Risk",
                "canonical": "북미 고금리 장기화에 따른 건설장비 수요 둔화",
                "source_span": "북미 시장의 고금리 장기화로 건설장비 수요가 둔화된 것",
                "section": "3분기 실적",
            },
        ],
        "relations": [
            {
                "source": "ent_001",
                "type": "HAS_METRIC",
                "target": "ent_002",
                "evidence": "두산밥캣은 2024년 3분기 영업이익이 전년 동기 대비 35% 감소했다고 공시했다",
            },
            {
                "source": "ent_001",
                "type": "FACES_RISK",
                "target": "ent_003",
                "evidence": "북미 시장의 고금리 장기화로 건설장비 수요가 둔화된 것이 주된 원인이다",
            },
        ],
    },
    ensure_ascii=False,
)


def _mock_llm(response: str) -> MagicMock:
    """LLMClient 대체 mock. .chat() 는 주어진 raw 문자열 반환."""
    llm = MagicMock()
    llm.config.model = "mock-model"
    llm.chat = MagicMock(return_value=response)
    return llm


# ── 테스트 ────────────────────────────────────────────
def test_extract_doosan_ideal_response():
    """이상적 LLM 응답 → ExtractionResult 채워짐 + 라벨 / 관계 검증.

    Spike v0 와 달리:
    - Metric 이 하나로 통합 (`ent_002` 1개)
    - 건설장비 수요 둔화는 Risk (Outlook 아님)
    - HAS_METRIC, FACES_RISK 두 관계 추출
    """
    llm = _mock_llm(DOOSAN_IDEAL_RESPONSE)
    chunks = [{"doc_id": "doosan-2024Q3", "section": "3분기 실적", "text": DOOSAN_TEXT}]

    result = asyncio.run(extract(chunks, llm=llm))

    # 기본 수량
    assert len(result.entities) == 3
    assert len(result.relations) == 2

    # v0 → v1 개선점 1: Metric 통합 (1개)
    metrics = [e for e in result.entities if e.type == EntityType.METRIC]
    assert len(metrics) == 1
    assert "35% 감소" in metrics[0].canonical
    assert "2024Q3" in metrics[0].canonical

    # v0 → v1 개선점 2: Risk 로 정확 분류 (Outlook 아님)
    risks = [e for e in result.entities if e.type == EntityType.RISK]
    outlooks = [e for e in result.entities if e.type == EntityType.OUTLOOK]
    assert len(risks) == 1
    assert len(outlooks) == 0

    # v0 → v1 개선점 3: Relation 존재
    rel_types = {r.type for r in result.relations}
    assert RelationType.HAS_METRIC in rel_types
    assert RelationType.FACES_RISK in rel_types


def test_extract_empty_chunk_graceful():
    """빈 청크 → LLM 호출 없이 빈 결과."""
    llm = _mock_llm("{\"entities\": [], \"relations\": []}")
    chunks = [{"doc_id": "doc-1", "section": "⎚", "text": ""}]

    result = asyncio.run(extract(chunks, llm=llm))

    assert result.entities == []
    assert result.relations == []
    # 핵심: LLM 은 호출되지 않아야 함 (빈 청크 그래이스풀 대응)
    llm.chat.assert_not_called()


def test_extract_unknown_label_dropped():
    """알 수 없는 EntityType / RelationType 은 graceful drop."""
    bad_response = json.dumps(
        {
            "entities": [
                {"local_id": "e1", "type": "Company", "canonical": "X", "source_span": "X"},
                {"local_id": "e2", "type": "Person", "canonical": "Y", "source_span": "Y"},  # 수락✕
            ],
            "relations": [
                # source 가 드롭된 e2 참조 → drop
                {"source": "e2", "type": "HAS_METRIC", "target": "e1", "evidence": "..."},
            ],
        }
    )
    llm = _mock_llm(bad_response)
    chunks = [{"doc_id": "doc-1", "section": "S", "text": "abc"}]

    result = asyncio.run(extract(chunks, llm=llm))

    # Person 라벨 드롭 → 1개만 남음
    assert len(result.entities) == 1
    assert result.entities[0].type == EntityType.COMPANY
    # source 가 드롭된 entity 참조 → 관계도 drop
    assert result.relations == []


def test_extract_invalid_json_graceful():
    """JSON 파싱 실패 → 빈 결과, 예외 안 떨어짐."""
    llm = _mock_llm("this is not json at all")
    chunks = [{"doc_id": "doc-1", "section": "S", "text": "abc"}]

    result = asyncio.run(extract(chunks, llm=llm))

    assert result.entities == []
    assert result.relations == []


def test_extract_codefence_stripped():
    """\`\`\`json ... \`\`\` 래핑되어 와도 정상 파싱."""
    fenced = f"```json\n{DOOSAN_IDEAL_RESPONSE}\n```"
    llm = _mock_llm(fenced)
    chunks = [{"doc_id": "doosan-2024Q3", "section": "3분기 실적", "text": DOOSAN_TEXT}]

    result = asyncio.run(extract(chunks, llm=llm))
    assert len(result.entities) == 3
