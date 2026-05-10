"""kg/linking.py 단위 테스트.

bge-m3 다운로드 피하기 위해 `embeddings` 를 직접 주입하는 방식.
실제 모델 검증은 PR 본문의 종합 검증 스크립트에서.
"""

from __future__ import annotations

import numpy as np

from kg.linking import (
    DEFAULT_THRESHOLD,
    EntityGroup,
    LinkingResult,
    link_entities,
    normalize_name,
)
from kg.ontology import EntityType, ExtractedEntity


# ── helper ───────────────────────────────────────────────
def _ent(local_id: str, type_: EntityType, canonical: str, source_span: str | None = None) -> ExtractedEntity:
    return ExtractedEntity(
        local_id=local_id,
        type=type_,
        canonical=canonical,
        source_span=source_span or canonical,
        section="S",
    )


def _stub_embeddings(rows: list[list[float]]) -> np.ndarray:
    """행별로 명시된 임베딩. L2 normalize 될 것으로 가정 (cosine 은 dot 과 같아짐)."""
    arr = np.asarray(rows, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.where(norms == 0, 1.0, norms)


# ── normalize_name ──────────────────────────────────────────
def test_normalize_strips_legal_suffixes():
    assert normalize_name("두산밥캣㈜") == "두산밥캣"
    assert normalize_name("두산밥캣(주)") == "두산밥캣"
    assert normalize_name("Doosan Bobcat Inc.") == "Doosan Bobcat"
    assert normalize_name("삼성전자 Co., Ltd.") == "삼성전자"


def test_normalize_strips_ticker():
    assert normalize_name("삼성전자(005930)") == "삼성전자"
    assert normalize_name("현대차(005380)") == "현대차"


def test_normalize_collapses_whitespace():
    assert normalize_name("두산  밥캣") == "두산 밥캣"
    assert normalize_name("  한화에어로스페이스  ") == "한화에어로스페이스"


# ── linking ────────────────────────────────────────────────
def test_link_empty_returns_empty():
    result = link_entities([])
    assert result.raw_count == 0
    assert result.grouped_count == 0
    assert result.groups == []


def test_link_high_similarity_same_type_grouped():
    """동일 type · cosine >= threshold → 한 그룹.

    한글 우선 정책 (#14 fix 6728274) 검증:
    - e2 (Doosan Bobcat) source_span 이 13자로 최장이지만 영문이라 제외
    - 한글 멤버 (e1, e3) 중 source_span 최장 = e3 의 'two산밥캣 주식회사' (8자)
    - 따라서 대표 = e3 의 canonical = "두산밥캣㈜"
    """
    ents = [
        _ent("e1", EntityType.COMPANY, "두산밥캣", "두산밥캣"),
        _ent("e2", EntityType.COMPANY, "Doosan Bobcat", "Doosan Bobcat"),
        _ent("e3", EntityType.COMPANY, "두산밥캣㈜", "두산밥캣 주식회사"),
    ]
    # 3개 모두 유사도 0.95 (threshold 0.92 초과)
    embs = _stub_embeddings([
        [1.0, 0.0],
        [0.95, 0.05],
        [0.97, 0.03],
    ])

    result = link_entities(ents, embeddings=embs, threshold=DEFAULT_THRESHOLD)

    assert result.raw_count == 3
    assert result.grouped_count == 1
    g = result.groups[0]
    assert g.type == EntityType.COMPANY
    assert len(g.members) == 3
    # 한글 우선 정책으로 e3 의 canonical 이 대표
    assert g.representative_name == "두산밥캣㈜"


def test_link_all_english_falls_back_to_longest():
    """그룹 멤버 전원이 영문이면 영문 최장으로 fallback.

    외국 회사 (예: Apple, Apple Inc., AAPL) 케이스 대응.
    """
    ents = [
        _ent("e1", EntityType.COMPANY, "Apple", "Apple"),
        _ent("e2", EntityType.COMPANY, "Apple Inc.", "Apple Inc."),
        _ent("e3", EntityType.COMPANY, "AAPL", "AAPL"),
    ]
    embs = _stub_embeddings([
        [1.0, 0.0],
        [0.97, 0.03],
        [0.95, 0.05],
    ])

    result = link_entities(ents, embeddings=embs, threshold=DEFAULT_THRESHOLD)

    assert result.grouped_count == 1
    # 한글 멤버 없음 → source_span 최장 = "Apple Inc." (10자)
    assert result.groups[0].representative_name == "Apple Inc."


def test_link_low_similarity_split():
    """다른 회사 (유사도 낮음) → 다른 그룹."""
    ents = [
        _ent("e1", EntityType.COMPANY, "삼성전자"),
        _ent("e2", EntityType.COMPANY, "삼성SDI"),
    ]
    embs = _stub_embeddings([
        [1.0, 0.0],
        [0.5, 0.866],  # cosine = 0.5 < 0.92
    ])

    result = link_entities(ents, embeddings=embs, threshold=DEFAULT_THRESHOLD)

    assert result.grouped_count == 2
    types = {g.type for g in result.groups}
    assert types == {EntityType.COMPANY}


def test_link_type_isolation():
    """동일 임베딩도 type 이 다르면 별도 그룹 (false merge 방지)."""
    ents = [
        _ent("e1", EntityType.COMPANY, "삼성전자"),
        _ent("e2", EntityType.RISK, "삼성전자"),  # 우연히 같은 텍스트
    ]
    embs = _stub_embeddings([
        [1.0, 0.0],
        [1.0, 0.0],  # cosine = 1.0 하지만 type 이 다름
    ])

    result = link_entities(ents, embeddings=embs, threshold=DEFAULT_THRESHOLD)

    # type 다르면 있을 수 없이 분리
    assert result.grouped_count == 2
    types = sorted(g.type.value for g in result.groups)
    assert types == ["Company", "Risk"]


def test_link_threshold_boundary():
    """threshold 정확히 경계에서의 동작."""
    ents = [
        _ent("e1", EntityType.METRIC, "A"),
        _ent("e2", EntityType.METRIC, "B"),
    ]
    # cosine = 0.92 정확히 경계 (>= 이므로 그룹화)
    embs = _stub_embeddings([
        [1.0, 0.0],
        [0.92, np.sqrt(1 - 0.92**2)],
    ])

    result = link_entities(ents, embeddings=embs, threshold=0.92)
    assert result.grouped_count == 1

    # threshold 0.93 이면 분리
    result_strict = link_entities(ents, embeddings=embs, threshold=0.93)
    assert result_strict.grouped_count == 2


def test_link_compression_ratio():
    """압축률 계산 검증."""
    ents = [_ent(f"e{i}", EntityType.COMPANY, "X") for i in range(10)]
    # 전부 같은 임베딩 → 한 그룹으로 압축
    embs = _stub_embeddings([[1.0, 0.0]] * 10)

    result = link_entities(ents, embeddings=embs, threshold=DEFAULT_THRESHOLD)
    assert result.raw_count == 10
    assert result.grouped_count == 1
    assert result.compression_ratio == 0.1
