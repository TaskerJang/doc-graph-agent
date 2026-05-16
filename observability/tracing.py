"""Opik 트레이싱 wrapper — `@track` 데코레이터 + 환경 미설정 시 no-op.

이 모듈의 책임:

1. **환경 변수 (`OPIK_API_KEY` / `OPIK_WORKSPACE` / `OPIK_PROJECT_NAME` /
   `OPIK_URL_OVERRIDE`) 가 모두 설정되어 있으면** Opik 의 `@track` 을 그대로
   노출 — Comet 서버에 trace 전송.

2. **하나라도 비어 있으면 graceful no-op** — 데코레이터가 원본 함수를 그대로
   반환. 테스트 환경 / CI / 신규 컨트리뷰터의 로컬 환경 보호.

3. **lazy init + .env 자동 로드** — `is_active()` 첫 호출 시점에 `.env` 를
   읽어 환경변수에 채워 넣는다 (이미 설정된 값은 덮지 않음). 호출 스크립트가
   `load_dotenv()` 를 깜빡해도 tracer 가 자기 책임으로 환경을 확보.

4. **opik 자체 import 도 지연** — 활성 상태일 때만 시도 → opik 패키지가
   없거나 망가졌어도 본 모듈 import 가 레포 전체를 깨트리지 않도록.

설계 사유 (이슈 #24 본문 + 5/16 sanity run 시행착오):
- Opik 의 raw `@track` 은 환경변수가 없어도 함수는 동작하지만 매 호출마다
  stderr 에 "API key must be specified" 경고를 뱉어 테스트 출력이 시끄러워짐.
- pytest 가 stderr 도 캡처하는 환경에서 운영 정보 노이즈 → 본 wrapper 로 격리.

5/16 sanity run 박제:
- `scripts/run_w3_pipeline.py` 가 `load_dotenv()` 를 호출 안 해서 tracer 가
  no-op 모드로 떨어짐. Neo4j / Kimi 는 각 모듈이 자체 로드하므로 동작했지만
  Opik 만 trace 가 안 떠 "왜 안 되지" 디버깅. 본 모듈이 `.env` 를 자기
  책임으로 로드하면 호출 스크립트가 깜빡해도 안전.

관련 이슈: #24 (본 작업), #6 (Opik 계정).
관련 모듈: `observability/README.md` 의 모듈 명세 (`tracing.py`).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ── 환경 변수 키 ─────────────────────────────────────────────
# `.env.example` 의 [Opik (Comet)] 섹션과 동일.
_REQUIRED_ENV_VARS = (
    "OPIK_API_KEY",
    "OPIK_WORKSPACE",
    "OPIK_PROJECT_NAME",
)
# `OPIK_URL_OVERRIDE` 는 self-hosted 시에만 필요 — required 에서 제외.


# ── .env 자동 로드 (idempotent) ──────────────────────────────
_dotenv_loaded: bool = False


def _ensure_dotenv_loaded() -> None:
    """`.env` 를 한 번만 로드. python-dotenv 가 없으면 graceful skip.

    `load_dotenv()` 의 기본 동작 (override=False) 을 따라 이미 set 된 환경
    변수는 덮지 않음 — 운영 환경에서 시스템 env 가 .env 보다 우선.
    """
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    try:
        from dotenv import load_dotenv  # local import — 선택적 의존성
        load_dotenv()
        _dotenv_loaded = True
    except ImportError:
        # python-dotenv 미설치 — 운영자가 시스템 env 로 직접 설정한 환경에서는
        # 정상. dotenv 없이도 본 wrapper 의 활성/비활성 판정은 동작.
        _dotenv_loaded = True  # 재시도 방지


# ── 활성 상태 판정 (lazy + 캐시) ────────────────────────────
_active: bool | None = None


def is_active() -> bool:
    """Opik 트레이싱이 활성 상태인지 (필수 env 모두 set & 비어있지 않음).

    첫 호출 시 `.env` 로드 후 환경변수를 한 번 읽고 그 결과를 캐시. 테스트
    에서 환경변수를 바꾼 뒤 재평가하고 싶으면 `reset_cache()` 호출.
    """
    global _active
    if _active is None:
        _ensure_dotenv_loaded()
        _active = all(os.environ.get(k, "").strip() for k in _REQUIRED_ENV_VARS)
        if _active:
            logger.info(
                "Opik 트레이싱 활성 — workspace=%s project=%s",
                os.environ.get("OPIK_WORKSPACE"),
                os.environ.get("OPIK_PROJECT_NAME"),
            )
        else:
            missing = [k for k in _REQUIRED_ENV_VARS if not os.environ.get(k, "").strip()]
            logger.info(
                "Opik 트레이싱 비활성 — @track 은 no-op (missing env: %s)",
                ", ".join(missing),
            )
    return _active


def reset_cache() -> None:
    """is_active() + .env 로드 캐시 초기화. 테스트에서 env 변경 후 재평가용."""
    global _active, _dotenv_loaded
    _active = None
    _dotenv_loaded = False


# ── 데코레이터 ───────────────────────────────────────────────
def track(*dargs: Any, **dkwargs: Any) -> Any:
    """Opik `@track` 의 graceful wrapper.

    사용 패턴 (Opik 원본과 동일):
        @track
        def f(...): ...

        @track(name="custom")
        def g(...): ...

        @track
        async def h(...): ...

    동작:
    - 활성 (필수 env 모두 set) → `opik.track` 그대로 위임
    - 비활성                  → 원본 함수 그대로 반환 (no-op)

    `@track` (bare) 과 `@track(...)` (parameterized) 둘 다 지원.
    """
    # bare 사용 — `@track` (인자 없이 함수에 직접 적용)
    if len(dargs) == 1 and not dkwargs and callable(dargs[0]):
        fn = dargs[0]
        if not is_active():
            return fn
        return _opik_track()(fn)

    # parameterized 사용 — `@track(name=..., tags=...)`
    if not is_active():
        # 데코레이터를 반환하되 함수를 그대로 통과
        def _passthrough(fn: F) -> F:
            return fn

        return _passthrough

    return _opik_track()(*dargs, **dkwargs)


# ── 내부: opik import 지연 ─────────────────────────────────────
def _opik_track() -> Callable[..., Any]:
    """opik 의 track 데코레이터를 lazy import. 활성 상태에서만 호출됨.

    별도 함수로 빼둔 이유: opik 패키지가 설치되어 있지 않거나 import 시
    예외가 나면, 본 wrapper 가 graceful 하게 no-op 으로 떨어지도록.
    """
    try:
        from opik import track as _track  # local import
        return _track
    except Exception as exc:
        logger.warning(
            "opik import 실패 — @track no-op 으로 폴백 (%s)", exc,
        )
        _active_off()
        # passthrough 데코레이터

        def _decorator(*dargs: Any, **dkwargs: Any) -> Any:
            if len(dargs) == 1 and not dkwargs and callable(dargs[0]):
                return dargs[0]

            def _identity(fn: F) -> F:
                return fn

            return _identity

        return _decorator


def _active_off() -> None:
    """내부용 — opik import 실패 시 캐시를 False 로 박아 재시도 방지."""
    global _active
    _active = False


__all__ = ["track", "is_active", "reset_cache"]
