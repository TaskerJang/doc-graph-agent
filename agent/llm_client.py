"""LLM 클라이언트 thin wrapper.

OpenAI SDK 호환 (Kimi, OpenRouter, OpenAI 모두 동일 코드로).
환경변수로 provider 토글:
- KIMI_API_KEY / KIMI_BASE_URL / KIMI_MODEL

Spike (#8) 검증용 최소 구현. 정식화는 #7 W2 환경 부트스트랩에서.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()


@dataclass(frozen=True)
class LLMConfig:
    """LLM 호출 설정. 환경변수로부터 로드."""

    api_key: str
    base_url: str
    model: str

    @classmethod
    def from_env(cls) -> "LLMConfig":
        api_key = os.environ.get("KIMI_API_KEY", "")
        base_url = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
        model = os.environ.get("KIMI_MODEL", "moonshot-v1-8k")
        if not api_key:
            raise RuntimeError(
                "KIMI_API_KEY 가 .env 에 없습니다. "
                "OpenRouter 또는 멘토 배부 키를 설정하세요."
            )
        return cls(api_key=api_key, base_url=base_url, model=model)


class LLMClient:
    """OpenAI SDK 기반 thin wrapper.

    - 단일 진입점: chat(messages, **kwargs)
    - tenacity 로 재시도 (네트워크 / 일시적 5xx 대비)
    - 토큰 / latency 로깅은 #24 Opik 통합에서 추가
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
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
        """단순 텍스트 응답 반환. Spike 단계 최소 인터페이스."""
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
        """헬스체크 1회 호출. Spike #8 단계 3 검증용."""
        return self.chat(
            messages=[{"role": "user", "content": "한 단어로 'pong' 만 답하세요."}],
            max_tokens=16,
        )
