"""observability/tracing.py 단위 테스트.

검증 포인트:
- 필수 env 미설정 시: `is_active() is False`, `@track` 은 원본 함수 그대로 반환
- 필수 env 설정 시:  `is_active() is True`, `@track` 은 opik 의 wrapper 위임
- bare 사용 (`@track`) 과 parameterized 사용 (`@track(name=...)`) 모두 동작
- async 함수에도 부착 가능
- 데코레이터가 원본 함수 동작을 손상시키지 않는다 (signature, return)
"""

from __future__ import annotations

import asyncio

import pytest

from observability import tracing


# ── fixtures ─────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_cache_each_test():
    """매 테스트 시작 전 캐시 초기화 — env 토글이 즉시 반영되도록."""
    tracing.reset_cache()
    yield
    tracing.reset_cache()


@pytest.fixture
def env_unset(monkeypatch: pytest.MonkeyPatch):
    """모든 OPIK_* 환경변수를 비움 → no-op 모드."""
    for k in ("OPIK_API_KEY", "OPIK_WORKSPACE", "OPIK_PROJECT_NAME", "OPIK_URL_OVERRIDE"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def env_set(monkeypatch: pytest.MonkeyPatch):
    """필수 OPIK_* 를 모두 채움 → 활성 모드."""
    monkeypatch.setenv("OPIK_API_KEY", "test-key")
    monkeypatch.setenv("OPIK_WORKSPACE", "test-ws")
    monkeypatch.setenv("OPIK_PROJECT_NAME", "test-proj")


# ── is_active() ──────────────────────────────────────────────
def test_is_active_false_when_no_env(env_unset):
    assert tracing.is_active() is False


def test_is_active_false_when_partial_env(monkeypatch: pytest.MonkeyPatch):
    """일부만 설정되어 있으면 비활성 (전부 또는 전무 원칙).""" 
    monkeypatch.setenv("OPIK_API_KEY", "k")
    monkeypatch.setenv("OPIK_WORKSPACE", "w")
    monkeypatch.delenv("OPIK_PROJECT_NAME", raising=False)
    assert tracing.is_active() is False


def test_is_active_false_when_empty_string(monkeypatch: pytest.MonkeyPatch):
    """빈 문자열도 미설정으로 취급 — `.env` 의 placeholder 보호."""
    monkeypatch.setenv("OPIK_API_KEY", "")
    monkeypatch.setenv("OPIK_WORKSPACE", "w")
    monkeypatch.setenv("OPIK_PROJECT_NAME", "p")
    assert tracing.is_active() is False


def test_is_active_true_when_all_env_set(env_set):
    assert tracing.is_active() is True


# ── @track no-op 모드 ────────────────────────────────────────
def test_track_bare_no_op_returns_original(env_unset):
    """`@track` (bare) on no-op 모드 → 원본 함수 그대로."""

    def f(x):
        return x * 2

    wrapped = tracing.track(f)
    assert wrapped is f
    assert wrapped(5) == 10


def test_track_parameterized_no_op_returns_original(env_unset):
    """`@track(name=...)` on no-op 모드 → 원본 함수 그대로."""

    @tracing.track(name="custom", tags=["x"])
    def f(x):
        return x + 1

    assert f(3) == 4


def test_track_no_op_preserves_async(env_unset):
    """`@track` 이 async 함수에서도 안전 (no-op 모드)."""

    @tracing.track
    async def g(x):
        return x * 3

    assert asyncio.run(g(4)) == 12


def test_track_no_op_keeps_function_identity(env_unset):
    """no-op 모드에서 wrapper 가 함수의 __name__ / 정체성을 망가뜨리지 않는다."""

    def original(x):
        """docstring 유지 테스트."""
        return x

    wrapped = tracing.track(original)
    # no-op 이므로 함수 객체가 동일
    assert wrapped is original
    assert wrapped.__name__ == "original"
    assert "docstring" in (wrapped.__doc__ or "")


# ── @track 활성 모드 (opik 위임) ─────────────────────────────
def test_track_bare_active_returns_callable(env_set):
    """활성 모드에서도 데코레이터가 callable 을 반환하고 호출 가능."""

    @tracing.track
    def f(x):
        return x + 100

    # opik 의 wrapper 가 씌워졌으므로 함수 객체는 다를 수 있지만 호출은 동작
    assert callable(f)
    assert f(1) == 101


def test_track_parameterized_active(env_set):
    """`@track(name=...)` 도 활성 모드에서 정상 동작."""

    @tracing.track(name="my-span", tags=["unit"])
    def f(x):
        return x ** 2

    assert callable(f)
    assert f(3) == 9


def test_track_active_async(env_set):
    """async 함수 + 활성 모드."""

    @tracing.track
    async def g(x):
        return x - 1

    assert asyncio.run(g(10)) == 9


# ── reset_cache() ────────────────────────────────────────────
def test_reset_cache_re_evaluates(monkeypatch: pytest.MonkeyPatch):
    """env 변경 후 reset_cache() 호출 시 활성 상태가 재평가됨."""
    # 시작: unset
    for k in ("OPIK_API_KEY", "OPIK_WORKSPACE", "OPIK_PROJECT_NAME"):
        monkeypatch.delenv(k, raising=False)
    assert tracing.is_active() is False

    # 채우고
    monkeypatch.setenv("OPIK_API_KEY", "k")
    monkeypatch.setenv("OPIK_WORKSPACE", "w")
    monkeypatch.setenv("OPIK_PROJECT_NAME", "p")
    # 캐시가 아직 False 상태
    assert tracing.is_active() is False

    # 리셋 후 재평가
    tracing.reset_cache()
    assert tracing.is_active() is True
