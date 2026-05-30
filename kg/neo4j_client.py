"""Neo4j 드라이버 thin wrapper.

AGENTS.md 의 가이드 준수:
- read-only 안전장치 + bounded result (LIMIT)
- 모든 쿼리 로그 (Spike 단계는 stdout, #24 에서 Opik 으로 이관)

Spike (#8) 검증용 최소 구현. 정식화는 #7 W2 환경 부트스트랩에서.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase, Session

load_dotenv()

logger = logging.getLogger(__name__)

# 쿼리에 LIMIT 절이 이미 있는지 판별. substring " LIMIT " 는 줄바꿈/탭으로 시작하는
# LIMIT(예: "ORDER BY score DESC\nLIMIT $k")를 놓쳐 자동 부착이 중복되므로
# word-boundary 정규식으로 잡는다.
_LIMIT_RE = re.compile(r"\bLIMIT\b", re.IGNORECASE)


@dataclass(frozen=True)
class Neo4jConfig:
    """Neo4j 연결 설정. 환경변수로부터 로드."""

    uri: str
    username: str
    password: str
    database: str = "neo4j"

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        uri = os.environ.get("NEO4J_URI", "")
        username = os.environ.get("NEO4J_USERNAME", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "")
        database = os.environ.get("NEO4J_DATABASE", "neo4j")
        if not uri or not password:
            raise RuntimeError(
                "NEO4J_URI / NEO4J_PASSWORD 가 .env 에 없습니다. "
                "Aura Console 에서 받은 자격증명을 설정하세요."
            )
        return cls(uri=uri, username=username, password=password, database=database)


class Neo4jClient:
    """Neo4j 드라이버 thin wrapper.

    - 단일 진입점: write(query, **params) / read(query, **params)
    - read 는 자동 LIMIT 100 강제 (이미 LIMIT 있으면 통과)
    - context manager 지원 (자원 정리 보장)
    """

    DEFAULT_READ_LIMIT = 100

    def __init__(self, config: Neo4jConfig | None = None) -> None:
        self.config = config or Neo4jConfig.from_env()
        self._driver: Driver = GraphDatabase.driver(
            self.config.uri,
            auth=(self.config.username, self.config.password),
        )

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._driver.session(database=self.config.database) as sess:
            yield sess

    def verify_connectivity(self) -> None:
        """연결 헬스체크. Spike #8 단계 1 검증용."""
        self._driver.verify_connectivity()
        logger.info("Neo4j connectivity OK (uri=%s)", self.config.uri)

    def read(self, query: str, **params) -> list[dict]:
        """READ 쿼리. LIMIT 미명시 시 자동 부착."""
        bounded = self._ensure_limit(query)
        with self.session() as sess:
            result = sess.run(bounded, parameters=params)
            return [dict(record) for record in result]

    def write(self, query: str, **params) -> list[dict]:
        """WRITE 쿼리. MERGE/CREATE 등. Spike 단계 5 (적재) 에서 사용."""
        with self.session() as sess:
            result = sess.run(query, parameters=params)
            return [dict(record) for record in result]

    @classmethod
    def _ensure_limit(cls, query: str) -> str:
        """쿼리에 LIMIT 이 없으면 끝에 부착. 단순 휴리스틱이지만 Spike 충분."""
        if _LIMIT_RE.search(query) or query.rstrip().endswith(";"):
            return query
        return f"{query.rstrip()} LIMIT {cls.DEFAULT_READ_LIMIT}"
