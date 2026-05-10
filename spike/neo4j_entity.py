"""Spike 검증 (#8): Neo4j + Entity 추출 1회 검증.

5단계 통과 확인:
1. Neo4j 연결          → Neo4jClient.verify_connectivity()
2. (의존성 설치)       → uv add 시점에 검증됨
3. Kimi hello-world    → LLMClient.hello()
4. Entity 추출         → extract_entities()
5. Neo4j MERGE         → load_entities() + 검증 read

실행:
    uv run python -m spike.neo4j_entity

DoD:
    실행 결과 마지막에 "✅ Spike 5/5 통과" 가 떠야 함.
    실패 시 어느 단계에서 막혔는지 stderr 에 명시.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from pydantic import BaseModel, Field

from agent.llm_client import LLMClient
from kg.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


# Spike 검증용 한국어 금융 문장 1개. 짧고 Entity 가 분명한 것.
SAMPLE_TEXT = (
    "두산밥캣은 2024년 3분기 영업이익이 전년 동기 대비 35% 감소했다고 공시했다. "
    "북미 시장의 고금리 장기화로 건설장비 수요가 둔화된 것이 주된 원인이다."
)


# Entity 추출 응답 스키마. 본 작업은 #9 온톨로지 / #12 프롬프트에서 정식화.
# Spike 단계는 최소 4개 라벨만 검증.
ENTITY_LABELS = ["Company", "Metric", "Risk", "Outlook"]


class Entity(BaseModel):
    name: str = Field(..., description="표면형 그대로의 Entity 이름")
    label: str = Field(..., description=f"라벨, {ENTITY_LABELS} 중 하나")


class EntityList(BaseModel):
    entities: list[Entity]


# 시행착오 박제 (#8):
# - 초기 버전은 f-string + .format(text=text) 이중 처리로 KeyError: '"entities"' 발생.
# - 원인: f"""...{{...}}...""" 가 이미 한 번 escape 되어 결과 문자열엔 단일 {} 만 남고,
#   그 다음 .format() 이 JSON 의 {"entities"} 를 변수로 해석하면서 KeyError.
# - 수정: f-string 제거 + JSON 예시는 {{...}} 로 두어 .format() 단일 처리에 위임.
EXTRACTION_PROMPT = """당신은 한국어 금융 문서에서 Entity 를 추출하는 도우미입니다.

아래 텍스트에서 다음 라벨에 해당하는 Entity 를 모두 추출하세요:
- Company: 기업명
- Metric: 재무/실적 지표 (영업이익, 매출액 등)
- Risk: 위험 요인
- Outlook: 전망/예측

응답은 반드시 다음 JSON 형식만 (다른 텍스트 없이):
{{"entities": [{{"name": "...", "label": "..."}}, ...]}}

텍스트:
{text}
"""


def extract_entities(llm: LLMClient, text: str) -> list[Entity]:
    """Spike 단계 4: 한국어 1문단 → Entity 리스트."""
    prompt = EXTRACTION_PROMPT.format(text=text)
    raw = llm.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=512,
        response_format={"type": "json_object"},
    )
    logger.info("LLM raw response: %s", raw)

    try:
        data = json.loads(raw)
        parsed = EntityList(**data)
    except (json.JSONDecodeError, ValueError) as exc:
        # Spike 는 graceful 실패 — 시행착오 박제용
        logger.error("Entity 추출 응답 파싱 실패: %s", exc)
        logger.error("원본 응답: %s", raw)
        return []

    # 라벨 검증 (모르는 라벨 드롭, 시행착오 노트 재료)
    valid = [e for e in parsed.entities if e.label in ENTITY_LABELS]
    dropped = [e for e in parsed.entities if e.label not in ENTITY_LABELS]
    if dropped:
        logger.warning("알 수 없는 라벨 드롭: %s", dropped)

    return valid


def load_entities(neo: Neo4jClient, entities: list[Entity]) -> int:
    """Spike 단계 5: Entity 들을 Neo4j 에 MERGE.

    한 번 더 돌려도 중복 안 생기게 idempotent.
    Spike 단계는 라벨 동적 처리 안 하고 :Entity 단일 노드 + property 로 둠.
    (정식 라벨 분리는 #15 Neo4j 적재에서.)
    """
    if not entities:
        return 0

    query = """
    UNWIND $rows AS row
    MERGE (e:Entity {name: row.name})
    SET e.label = row.label, e.spike = true
    RETURN count(e) AS loaded
    """
    rows = [{"name": e.name, "label": e.label} for e in entities]
    result = neo.write(query, rows=rows)
    return int(result[0]["loaded"]) if result else 0


def verify_loaded(neo: Neo4jClient) -> list[dict[str, Any]]:
    """적재 결과 검증용 read."""
    query = """
    MATCH (e:Entity {spike: true})
    RETURN e.name AS name, e.label AS label
    ORDER BY e.label, e.name
    """
    return neo.read(query)


def cleanup(neo: Neo4jClient) -> None:
    """Spike 흔적 청소 (재실행 깔끔하게)."""
    neo.write("MATCH (e:Entity {spike: true}) DETACH DELETE e")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("=" * 60)
    print("Spike #8: Neo4j + Entity 추출 1회 검증")
    print("=" * 60)

    # ─── 단계 1: Neo4j 연결 ───
    print("\n[1/5] Neo4j 연결 확인 중...")
    try:
        neo = Neo4jClient()
        neo.verify_connectivity()
        print("    ✓ Neo4j 연결 OK")
    except Exception as exc:
        print(f"    ✗ Neo4j 연결 실패: {exc}", file=sys.stderr)
        return 1

    try:
        # ─── 단계 3: Kimi hello-world ───
        print("\n[3/5] LLM hello-world 호출 중...")
        try:
            llm = LLMClient()
            pong = llm.hello()
            print(f"    ✓ LLM 응답: {pong!r}")
        except Exception as exc:
            print(f"    ✗ LLM 호출 실패: {exc}", file=sys.stderr)
            return 1

        # ─── 단계 4: Entity 추출 ───
        print("\n[4/5] Entity 추출 중...")
        print(f"    입력: {SAMPLE_TEXT}")
        entities = extract_entities(llm, SAMPLE_TEXT)
        if not entities:
            print("    ✗ Entity 추출 실패 (빈 결과)", file=sys.stderr)
            return 1
        for e in entities:
            print(f"    ✓ {e.label:10s} {e.name}")

        # ─── 단계 5: Neo4j MERGE + 검증 ───
        print("\n[5/5] Neo4j 적재 + 검증 중...")
        cleanup(neo)  # 재실행 시 깨끗하게
        loaded = load_entities(neo, entities)
        print(f"    ✓ MERGE {loaded} 건")

        verified = verify_loaded(neo)
        print(f"    ✓ READ 검증 — {len(verified)} 건 조회됨:")
        for row in verified:
            print(f"        ({row['label']}) {row['name']}")

        if len(verified) != len(entities):
            print(
                f"    ✗ 적재 수 불일치 (추출 {len(entities)} / 조회 {len(verified)})",
                file=sys.stderr,
            )
            return 1

    finally:
        neo.close()

    print("\n" + "=" * 60)
    print("✅ Spike 5/5 통과")
    print("=" * 60)
    print("\n다음 단계: Neo4j Browser 에서 시각 확인")
    print('  MATCH (e:Entity {spike: true}) RETURN e')
    return 0


if __name__ == "__main__":
    sys.exit(main())
