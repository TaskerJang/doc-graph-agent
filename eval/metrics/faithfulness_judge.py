"""
eval/metrics/faithfulness_judge.py
LLM-as-Judge — Faithfulness / Completeness / Conciseness
참고: FineSurE (ACL 2024) + doc-summary-agent #127 PR

Claude / DeepSeek / Kimi 등 OpenRouter 경유 모델도 호환 (#127 C7):
- reasoning_effort 분기 (OpenAI 네이티브만 전달)
- strict json_schema 자동 fallback
- 빈 응답 진단 로깅
- reasoning OFF 3중 안전 (#53 후속 — 공식 문서 패턴)
"""
import logging
import os
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import RateLimitError, APITimeoutError, APIConnectionError, BadRequestError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.2"
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
MODEL = DEFAULT_MODEL

_active_judge_client: OpenAI = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
_active_judge_model: str = DEFAULT_MODEL
_judge_strict_schema_supported: bool = True
_use_openrouter_extras: bool = False


# ── Reasoning OFF for OpenRouter reasoning models ──────────
# 공식 문서: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
# claude-haiku-4.5 등 judge 모델이 reasoning 박힐 때 빈 응답 방지.
#
# 3중 안전:
#   - enabled: false  → Anthropic (claude) 지원
#   - max_tokens: 1   → 모든 모델 호환 (공식 권장)
#   - exclude: true   → reasoning 응답 전달 X
_REASONING_OFF_BODY = {
    "reasoning": {
        "enabled": False,
        "max_tokens": 1,
        "exclude": True,
    },
}


def configure_judge_llm(
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str = "OPENAI_API_KEY",
) -> None:
    global _active_judge_client, _active_judge_model, _judge_strict_schema_supported, _use_openrouter_extras
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise RuntimeError(f"환경변수 {api_key_env} 미설정 — Judge LLM 재설정 불가")
    _active_judge_client = OpenAI(api_key=api_key, base_url=base_url)
    if model is not None:
        _active_judge_model = model
    _judge_strict_schema_supported = (base_url is None)
    _use_openrouter_extras = base_url is not None and "openrouter" in base_url.lower()
    logger.info(
        "Judge LLM 재설정: model=%s base_url=%s api_key_env=%s strict_schema=%s openrouter=%s",
        _active_judge_model, base_url, api_key_env,
        _judge_strict_schema_supported, _use_openrouter_extras,
    )


_PROMPTS_DIR = Path(__file__).parent / "prompts"
FAITHFULNESS_PROMPT           = (_PROMPTS_DIR / "faithfulness_v1.md").read_text(encoding="utf-8")
NUMERICAL_FAITHFULNESS_PROMPT = (_PROMPTS_DIR / "numerical_faithfulness_v1.md").read_text(encoding="utf-8")


def _relax_schema(response_format: dict) -> dict:
    return {"type": "json_object"}


def _is_openai_native_model(model: str) -> bool:
    m = model.lower()
    if m.startswith("gpt-") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
        return True
    if m.startswith("openai/"):
        return True
    return False


@retry(
    retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError)),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _call_api(prompt: str, response_format: dict) -> dict:
    global _judge_strict_schema_supported
    import json

    rf = response_format if _judge_strict_schema_supported else _relax_schema(response_format)

    call_kwargs = {
        "model": _active_judge_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": 2000,
        "response_format": rf,
        "timeout": 60,  # 30 → 60s (reasoning 모델 대응)
    }

    # Model-specific 분기:
    # - OpenAI 네이티브 (gpt-*, o-series): reasoning_effort="low" 전달
    # - OpenRouter 경유 (Claude, DeepSeek, Kimi 등): extra_body 로 reasoning OFF 3중
    if _is_openai_native_model(_active_judge_model):
        call_kwargs["reasoning_effort"] = "low"
    elif _use_openrouter_extras:
        call_kwargs["extra_body"] = _REASONING_OFF_BODY

    try:
        response = _active_judge_client.chat.completions.create(**call_kwargs)
    except BadRequestError as e:
        err_msg = str(e).lower()
        if "json_schema" in err_msg or "response_format" in err_msg or "strict" in err_msg:
            if _judge_strict_schema_supported:
                logger.warning("Judge strict json_schema 미지원 → json_object fallback: %s", e)
                _judge_strict_schema_supported = False
                call_kwargs["response_format"] = _relax_schema(response_format)
                response = _active_judge_client.chat.completions.create(**call_kwargs)
            else:
                raise
        else:
            raise

    raw_content = response.choices[0].message.content if response.choices else ""
    raw_content = (raw_content or "").strip()

    if not raw_content:
        msg = response.choices[0].message if response.choices else None
        reasoning_content = getattr(msg, "reasoning_content", None) if msg else None
        reasoning = getattr(msg, "reasoning", None) if msg else None
        finish_reason = response.choices[0].finish_reason if response.choices else "?"
        logger.warning(
            "Judge 응답 빈 content (model=%s finish_reason=%s) — fallback 시도",
            _active_judge_model, finish_reason,
        )
        # reasoning_content / reasoning 두 필드 모두 fallback
        for candidate in (reasoning_content, reasoning):
            if candidate and "{" in candidate:
                try:
                    start = candidate.find("{")
                    end = candidate.rfind("}")
                    if start >= 0 and end > start:
                        return json.loads(candidate[start:end+1])
                except (json.JSONDecodeError, ValueError):
                    continue
        return {}

    if raw_content.startswith("```"):
        raw_content = raw_content.split("```")[1]
        if raw_content.startswith("json"):
            raw_content = raw_content[4:]
        raw_content = raw_content.strip()

    return json.loads(raw_content)


def judge_faithfulness(source: str, summary: str) -> dict:
    prompt = FAITHFULNESS_PROMPT.format(source=source[:3000], summary=summary)
    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "faithfulness_result",
            "schema": {
                "type": "object",
                "properties": {
                    "faithfulness":          {"type": "string", "enum": ["Faithful", "Not Faithful"]},
                    "faithfulness_reason":   {"type": "string"},
                    "completeness":          {"type": "integer", "minimum": 1, "maximum": 5},
                    "completeness_reason":   {"type": "string"},
                    "conciseness":           {"type": "integer", "minimum": 1, "maximum": 5},
                    "conciseness_reason":    {"type": "string"},
                },
                "required": ["faithfulness", "faithfulness_reason",
                             "completeness", "completeness_reason",
                             "conciseness", "conciseness_reason"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
    try:
        return _call_api(prompt, schema)
    except Exception as e:
        logger.error("Faithfulness Judge 실패: %s", e)
        return {
            "faithfulness": "Error",
            "faithfulness_reason": str(e),
            "completeness": None,
            "completeness_reason": "",
            "conciseness": None,
            "conciseness_reason": "",
        }


def judge_numerical_faithfulness(source: str, summary: str) -> dict:
    prompt = NUMERICAL_FAITHFULNESS_PROMPT.format(source=source[:3000], summary=summary)
    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "numerical_faithfulness_result",
            "schema": {
                "type": "object",
                "properties": {
                    "numerical_faithfulness": {"type": "string", "enum": ["Correct", "Incorrect"]},
                    "reason":                 {"type": "string"},
                },
                "required": ["numerical_faithfulness", "reason"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
    try:
        return _call_api(prompt, schema)
    except Exception as e:
        logger.error("Numerical Faithfulness Judge 실패: %s", e)
        return {"numerical_faithfulness": "Error", "reason": str(e)}
