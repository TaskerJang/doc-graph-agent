"""NED + Dedup — 청크 간 동일 Entity 묶기 (표기 정규화 + Cosine 그룹화).

PR #38 에서 만든 `kg/extractor.py` 의 출력 (청크별 ExtractedEntity 리스트) 을
입력으로 받아 **동일 실체를 하나의 그룹으로 묶는다**.

파이프라인 (3단계):
  1. Normalize: 법인 접미사 제거 / 공백 정규화 / 종목코드 분리
  2. Embed:     bge-m3 로 canonical 텍스트 임베딩 (sentence-transformers)
  3. Group:     같은 type 안에서 cosine >= THRESHOLD 로 그룹화

설계 원칙:
- **Type 격리**: Company 는 Company 끼리만 비교. type 이 다르면 아무리 유사해도
  다른 그룹 (false merge 방지).
- **Threshold 보수적**: 0.92 는 회사 레포 차용. 넓은 merge 보다 좋은 split 이
  점진적 개선에 유리 (NED 는 false merge 가 안 돌아오는 속성).
- **대표 선정**: 그룹 내 최장 source_span 을 그룹명으로 (정보량 기준).

관련 이슈: #14 (본 작업), #13 (입력 공급 — PR #38), #15 (Neo4j 적재).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable

import numpy as np
from pydantic import BaseModel, Field

from kg.ontology import EntityType, ExtractedEntity

logger = logging.getLogger(__name__)


# ── 상수 ─────────────────────────────────────────
DEFAULT_EMBED_MODEL = "BAAI/bge-m3"

# Cosine threshold. 회사 레포 차용. NED 는 false merge 방지가 우선 → 높게.
# 너무 높으면 "두산밥캣" ≠ "두산밥캣 코리아" 같은 실수 발생 가능 → 검증 결과로 조정.
DEFAULT_THRESHOLD = 0.92

# 법인 접미사 — 정규화 단계에서 제거.
_LEGAL_SUFFIX_RE = re.compile(
    r"(㊐|\(주\)|주식회사|\(株\)|Inc\.?|Co\.?,?\s*Ltd\.?|Ltd\.?|Corp\.?|Co\.?)",
    re.IGNORECASE,
)

# 종목코드 괄호 — "삼성전자(005930)" → "삼성전자".
_TICKER_RE = re.compile(r"\(\d{4,6}\)\s*$")

# 공백 연속 압축.
_WHITESPACE_RE = re.compile(r"\s+")


# ── 결과 타입 ──────────────────────────────────────
class EntityGroup(BaseModel):
    """NED 로 묶인 동일 실체 그룹.

    `members` 는 원본 ExtractedEntity 들 (청크 간 중복 포함). 그룹 대표는
    `representative_name` 으로 (그룹 내 최장 source_span).
    """

    group_id:            str                      = Field(..., description="전역적 식별자. 예: 'grp_001'")
    type:                EntityType
    representative_name: str                      = Field(..., description="그룹 대표 이름 (최장 source_span)")
    members:             list[ExtractedEntity]    = Field(default_factory=list)


class LinkingResult(BaseModel):
    """linking() 의 출력.

    NED 단계의 수치 통계도 함께 반환 — 그룹화 완화/압축률 추적용.
    """

    groups:        list[EntityGroup]
    raw_count:     int = Field(..., description="입력 ExtractedEntity 수")
    grouped_count: int = Field(..., description="구성된 그룹 수")

    @property
    def compression_ratio(self) -> float:
        """입력 대비 그룹화 이후 축소 비율. 1.0 이면 압축 없음."""
        return self.grouped_count / max(self.raw_count, 1)


# ── 1단계: Normalize ───────────────────────────────────────
def normalize_name(name: str) -> str:
    """표기 정규화.

    - 종목코드 괄호 제거 (예: "삼성전자(005930)" → "삼성전자")
    - 법인 접미사 제거 (㊐, \\(주\\), Inc., Co., Ltd. 등)
    - 공백 압축
    - 양끝 공백 제거

    주의: 대소문자는 유지 (Kimi 의 canonical 이 이미 정규화 경향).
    """
    if not name:
        return ""
    n = _TICKER_RE.sub("", name)
    n = _LEGAL_SUFFIX_RE.sub("", n)
    n = _WHITESPACE_RE.sub(" ", n).strip()
    return n


# ── 2단계: Embed (bge-m3 지연 로딩) ───────────────────────────
@lru_cache(maxsize=1)
def _get_embedder(model_name: str = DEFAULT_EMBED_MODEL):
    """sentence-transformers 도 import 도 처음 호출 때만.

    이유: import 자체가 ~5s 걸리는 경우 있음. 테스트·다른 모듈 import 는
    이 함수를 고도로 이해 실제 임베다 사용 시점에만 로드.
    """
    logger.info("Loading embed model: %s (첫 호출 시 다운로드 5~10분 소요)", model_name)
    started = time.perf_counter()
    from sentence_transformers import SentenceTransformer  # local import

    model = SentenceTransformer(model_name)
    logger.info("Embed model loaded (%.1fs)", time.perf_counter() - started)
    return model


def embed_texts(
    texts: list[str],
    model_name: str = DEFAULT_EMBED_MODEL,
) -> np.ndarray:
    """텍스트 리스트 → (N, D) numpy 행렬. L2 normalize 되어 있어 cosine = dot."""
    if not texts:
        return np.zeros((0, 0))
    model = _get_embedder(model_name)
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,  # cosine 계산을 dot product 로 단순화
        show_progress_bar=False,
    )
    return np.asarray(embeddings, dtype=np.float32)


# ── 3단계: Group (cosine 그룹화) ────────────────────────────────
@dataclass
class _GroupBuilder:
    """Union-Find 와 유사한 단순한 누적 그룹 구성기.

    제약 조건:
    - type 이 같은 entity 끼리만 한 그룹에
    - 그룹 내의 아무 entity 와의 cosine >= threshold 면 합류
      (single-link 클러스터링 — chain 이 길면 false merge 위험 있으나
       threshold 0.92 이면 현실적 안전)
    """

    type: EntityType
    members: list[ExtractedEntity] = field(default_factory=list)
    embeddings: list[np.ndarray] = field(default_factory=list)

    def fits(self, e: ExtractedEntity, emb: np.ndarray, threshold: float) -> bool:
        if e.type != self.type:
            return False
        if not self.embeddings:
            return False
        sims = np.stack(self.embeddings) @ emb  # (k,) — 둘 다 L2 normalized
        return bool(sims.max() >= threshold)

    def add(self, e: ExtractedEntity, emb: np.ndarray) -> None:
        self.members.append(e)
        self.embeddings.append(emb)

    def representative_name(self) -> str:
        """그룹 내 가장 긴 source_span 을 대표로 (정보량 기준)."""
        return max(self.members, key=lambda m: len(m.source_span)).canonical


def _build_groups(
    entities: list[ExtractedEntity],
    embeddings: np.ndarray,
    threshold: float,
) -> list[_GroupBuilder]:
    """entities 와 embeddings 를 동기화해 그룹을 구성.

    이 함수는 입력 순서대로 순회하며, 이미 만들어진 그룹 중 적합한
    (type 같고 cosine 충족) 그룹이 있으면 그리로, 없으면 새 그룹을 엽니다.
    """
    groups: list[_GroupBuilder] = []
    for ent, emb in zip(entities, embeddings, strict=True):
        placed = False
        for g in groups:
            if g.fits(ent, emb, threshold):
                g.add(ent, emb)
                placed = True
                break
        if not placed:
            new_group = _GroupBuilder(type=ent.type)
            new_group.add(ent, emb)
            groups.append(new_group)
    return groups


# ── 공개 인터페이스 ─────────────────────────────────────
def link_entities(
    entities: Iterable[ExtractedEntity],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    model_name: str = DEFAULT_EMBED_MODEL,
    embeddings: np.ndarray | None = None,
) -> LinkingResult:
    """청크 간 동일 Entity 를 그룹화.

    파이프라인:
      Normalize → (provided embeddings 없으면 Embed) → Group

    테스트에서는 `embeddings` 를 주입해 bge-m3 다운로드를 피한다 (디퍼런시에).

    Args:
        entities: ExtractedEntity 리스트 (청크 간 중복 포함).
        threshold: cosine 이상이면 같은 그룹. 기본 0.92.
        model_name: bge-m3 외 다른 모델 테스트용.
        embeddings: (N, D) 미리 계산된 임베딩. None 이면 내부에서 계산.

    Returns:
        LinkingResult — 그룹 리스트 + 통계.
    """
    ents = list(entities)
    if not ents:
        return LinkingResult(groups=[], raw_count=0, grouped_count=0)

    # 1. Normalize: canonical 을 재수정 — 원본은 유지하고 normalize 는
    #    임베딩 입력 용으로만 사용 (canonical 자체는 보존 — 그룹 대표 선정용).
    norm_texts = [normalize_name(e.canonical) for e in ents]

    # 2. Embed (주입 아니면 로드)
    if embeddings is None:
        embeddings = embed_texts(norm_texts, model_name=model_name)
    if embeddings.shape[0] != len(ents):
        raise ValueError(
            f"embeddings 행 수 ({embeddings.shape[0]}) ≠ entity 수 ({len(ents)})"
        )

    # 3. Group
    builders = _build_groups(ents, embeddings, threshold)

    groups: list[EntityGroup] = []
    for idx, b in enumerate(builders):
        groups.append(
            EntityGroup(
                group_id=f"grp_{idx + 1:03d}",
                type=b.type,
                representative_name=b.representative_name(),
                members=list(b.members),
            )
        )

    result = LinkingResult(
        groups=groups,
        raw_count=len(ents),
        grouped_count=len(groups),
    )
    logger.info(
        "Linking 완료 raw=%d → groups=%d (compression=%.2f) threshold=%.2f",
        result.raw_count, result.grouped_count, result.compression_ratio, threshold,
    )
    return result
