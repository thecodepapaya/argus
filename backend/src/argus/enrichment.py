"""LLM-assisted, administrator-reviewed technology profile preparation."""

from __future__ import annotations

import re
from typing import Any

from argus.llm import LLMError, complete_json


PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string"},
        "display_name": {"type": "string"},
        "kind": {"type": "string"},
        "definition": {"type": "string"},
        "github_repos": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "hn_query": {"type": "string"},
        "news_query": {"type": "string"},
        "relevance_terms": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
    },
    "required": ["id", "display_name", "kind", "definition", "github_repos", "hn_query", "news_query", "relevance_terms"],
}


def _prompt(display_name: str, description: str) -> str:
    return f"""Prepare an editable ARGUS technology-tracking profile for an administrator.

Technology name: {display_name}
Administrator's description: {description}

Use web search only to resolve factual configuration details, especially official or canonical GitHub repositories. Do not invent repository names, vendors, citations, or claims. Return a concise definition that preserves the administrator's meaning. The slug must be lowercase hyphenated. `kind` is a short category such as protocol, framework, or developer tool. Build focused Hacker News and news queries and 3-12 relevance terms. Include only public GitHub owner/repository values you are confident are correct. This is a draft proposal: an administrator must inspect and edit every field before creating it."""


def enrich_profile(display_name: object, description: object) -> dict[str, Any]:
    name = str(display_name or "").strip()
    definition = str(description or "").strip()
    if not name or len(name) > 120:
        raise ValueError("A technology name of up to 120 characters is required")
    if not definition or len(definition) > 1000:
        raise ValueError("A technology description of up to 1000 characters is required")
    try:
        profile, metadata = complete_json(
            prompt=_prompt(name, definition), schema_name="technology_profile", schema=PROFILE_SCHEMA, use_web_search=True,
        )
    except LLMError as error:
        raise ValueError(str(error)) from error
    slug = str(profile.get("id", "")).strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("OpenRouter returned an invalid technology slug")
    repositories = profile.get("github_repos")
    terms = profile.get("relevance_terms")
    if not isinstance(repositories, list) or any(not isinstance(item, str) or not re.fullmatch(r"[^/\s]+/[^/\s]+", item) for item in repositories):
        raise ValueError("OpenRouter returned invalid GitHub repositories")
    if not isinstance(terms, list) or not terms or any(not isinstance(item, str) or not item.strip() for item in terms):
        raise ValueError("OpenRouter returned invalid relevance terms")
    return {"profile": profile, "provider": "openrouter", "model": metadata["model"], "review_required": True}
