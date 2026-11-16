from __future__ import annotations

import json
import os
from datetime import date
from urllib import error, request


class DeepSeekError(RuntimeError):
    pass


_request_counts: dict[date, int] = {}


def _provider_config() -> tuple[str, str, str, str]:
    provider = os.environ.get("AI_PROVIDER", "").strip().lower()
    if not provider and os.environ.get("DEEPSEEK_API_KEY", "").strip():
        provider = "deepseek"
    if provider == "deepseek":
        return (
            provider,
            os.environ.get("DEEPSEEK_API_KEY", "").strip(),
            os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
        )
    if provider == "groq":
        return (
            provider,
            os.environ.get("GROQ_API_KEY", "").strip(),
            os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
        )
    if provider == "openrouter":
        return (
            provider,
            os.environ.get("OPENROUTER_API_KEY", "").strip(),
            os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            os.environ.get("OPENROUTER_MODEL", ""),
        )
    return "", "", "", ""


def external_ai_enabled() -> bool:
    return bool(_provider_config()[0])


def _build_context(data: dict) -> str:
    return json.dumps(
        {
            "mode": data.get("mode"),
            "dashboard": data.get("dashboard"),
            "instances": data.get("instances", [])[:25],
            "recommendations": data.get("recommendations", [])[:10],
        },
        separators=(",", ":"),
    )


def ask_deepseek(question: str, data: dict) -> str:
    if len(question) > int(os.environ.get("AI_MAX_QUESTION_CHARS", "500")):
        raise DeepSeekError("Question is too long")

    today = date.today()
    max_requests = max(0, int(os.environ.get("AI_MAX_REQUESTS_PER_DAY", "20")))
    request_count = _request_counts.get(today, 0)
    if request_count >= max_requests:
        raise DeepSeekError("Daily AI request limit reached")

    provider, api_key, base_url, model = _provider_config()
    if not api_key:
        raise DeepSeekError(f"{provider or 'AI'} API key is not configured")
    if provider == "openrouter" and not model.endswith(":free"):
        raise DeepSeekError("OpenRouter is restricted to :free models by default")

    endpoint = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a cloud-cost assistant. Use only the supplied "
                    "monitoring context. Never claim an AWS action was taken. "
                    "Give concise, practical answers and mention when data is missing."
                ),
            },
            {"role": "user", "content": f"Context: {_build_context(data)}\nQuestion: {question}"},
        ],
        "stream": False,
        "max_tokens": max(1, int(os.environ.get("AI_MAX_OUTPUT_TOKENS", "300"))),
    }
    http_request = request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(http_request, timeout=30) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
        raise DeepSeekError("DeepSeek request failed") from exc

    try:
        answer = response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError("DeepSeek returned an unexpected response") from exc
    if not isinstance(answer, str) or not answer.strip():
        raise DeepSeekError("DeepSeek returned an empty answer")
    _request_counts[today] = request_count + 1
    return answer.strip()
