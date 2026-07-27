"""Small, dependency-free OpenRouter client for bounded admin assistance."""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-5.6-luna"


class LLMError(RuntimeError):
    """A safe, operator-facing error from the optional LLM service."""


def configured() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def complete_json(
    *,
    prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    api_key: str | None = None,
    model: str | None = None,
    use_web_search: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Request schema-bound JSON, with optional OpenRouter server-side web search."""
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise LLMError("OPENROUTER_API_KEY is not configured; LLM assistance is disabled")
    selected_model = model or os.environ.get("ARGUS_LLM_MODEL", DEFAULT_MODEL)
    payload: dict[str, Any] = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": "You are a careful research assistant. Return only data matching the requested JSON schema."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
        "provider": {"require_parameters": True},
    }
    if use_web_search:
        payload["tools"] = [{"type": "openrouter:web_search"}]
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "ARGUS/0.6",
        "X-Title": "ARGUS",
    }
    referer = os.environ.get("ARGUS_PUBLIC_URL")
    if referer:
        headers["HTTP-Referer"] = referer
    request = Request(OPENROUTER_ENDPOINT, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    response: dict[str, Any] | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=75) as raw:  # nosec B310: fixed OpenRouter HTTPS endpoint
                response = json.loads(raw.read().decode("utf-8"))
            break
        except HTTPError as error:
            detail = error.read(1000).decode("utf-8", errors="replace")
            if error.code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                raise LLMError(f"OpenRouter request failed with HTTP {error.code}: {detail}") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt == 2:
                raise LLMError(f"OpenRouter request failed: {error}") from error
        time.sleep(2 ** attempt)
    if response is None:
        raise LLMError("OpenRouter did not return a response")
    try:
        message = response["choices"][0]["message"]
        content = message["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty content")
        result = json.loads(content)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise LLMError("OpenRouter returned an invalid structured response") from error
    if not isinstance(result, dict):
        raise LLMError("OpenRouter returned a JSON value instead of an object")
    return result, {"model": response.get("model", selected_model), "message": message}
