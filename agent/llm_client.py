"""LLM 클라이언트 thin wrapper.

OpenAI SDK 호환 — Kimi, OpenRouter, OpenAI, DeepSeek, Grok 모두 동일 코드로.

## 환경변수 설정 방식 (#127 멘토링 평가 토글)

### 방식 1: 기본 KIMI_* (prod / W4 정성 검증)
- KIMI_API_KEY / KIMI_BASE_URL / KIMI_MODEL

### 방식 2: 평가 진입점에서 configure_llm()으로 명시 토글
- LLMConfig(api_key, base_url, model) 을 직접 주입
- scripts/run_qa_eval.py 에서 --llm-model / --llm-base-url / --llm-api-key-env 인자로 토글

호출 안 하면 KIMI_* 환경변수 사용 (기존 동작 유지).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMConfig:
    """LLM 호출 설정."""

    api_key: str
    base_url: str
    model: str

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """기본 — KIMI_* 환경변수에서 로드."""
        api_key = os.environ.get("KIMI_API_KEY", "")
        base_url = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
        model = os.environ.get("KIMI_MODEL", "moonshot-v1-8k")
        if not api_key:
            raise RuntimeError(
                "KIMI_API_KEY 가 .env 에 없습니다. "
                "OpenRouter 또는 멘토 배부 키를 설정하세요."
            )
        return cls(api_key=api_key, base_url=base_url, model=model)

    @classmethod
    def from_args(
        cls,
        model: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "KIMI_API_KEY",
    ) -> "LLMConfig":
        """평가 진입점용 — CLI 인자로 명시 토글 (#127).

        Args:
            model: 모델 ID (예: "deepseek/deepseek-v3.2")
            base_url: OpenAI-호환 endpoint (예: "https://openrouter.ai/api/v1")
            api_key_env: API 키 환경변수 이름 (예: "OPENROUTER_API_KEY")
        """
        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            raise RuntimeError(f"환경변수 {api_key_env} 미설정 — LLM 토글 불가")
        if not model:
            raise RuntimeError("--llm-model 인자 필요")
        if not base_url:
            raise RuntimeError("--llm-base-url 인자 필요")
        return cls(api_key=api_key, base_url=base_url, model=model)


# ── Runtime active config (#127) ───────────────────────────
# configure_llm() 호출 전: None → LLMClient() 호출 시 from_env() 사용
# configure_llm() 호출 후: 명시 config 사용 → 모든 LLMClient 인스턴스 영향
_active_config: LLMConfig | None = None


def configure_llm(
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str = "KIMI_API_KEY",
) -> None:
    """평가 진입점에서 LLM 을 일회성으로 재설정 (#127).

    호출 안 하면 기존 KIMI_* 환경변수 사용 (prod / W4 정성 검증 동작 유지).

    호출 시 모든 후속 LLMClient() 인스턴스가 이 config 를 사용 →
    retrieval.text2cypher / local_retriever / router 자동 토글.
    """
    global _active_config
    _active_config = LLMConfig.from_args(
        model=model, base_url=base_url, api_key_env=api_key_env
    )
    logger.info(
        "LLM 재설정: model=%s base_url=%s api_key_env=%s",
        _active_config.model, _active_config.base_url, api_key_env,
    )


class LLMClient:
    """OpenAI SDK 기반 thin wrapper.

    - 단일 진입점: chat(messages, **kwargs)
    - tenacity 로 재시도
    - configure_llm() 호출됐으면 그 config 사용, 안 됐으면 from_env()
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        if config is None:
            config = _active_config if _active_config is not None else LLMConfig.from_env()
        self.config = config
        self._client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        response_format: dict | None = None,
    ) -> str:
        kwargs: dict = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def hello(self) -> str:
        return self.chat(
            messages=[{"role": "user", "content": "한 단어로 'pong' 만 답하세요."}],
            max_tokens=16,
        )
