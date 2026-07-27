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

ENRICHMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string", "enum": ["ready", "reject"]},
        "reason": {"type": "string"},
        "profile": PROFILE_SCHEMA,
    },
    "required": ["decision", "reason", "profile"],
}


def _input_issue(name: str, definition: str) -> str | None:
    """Reject inputs that cannot identify a technology before calling the LLM."""
    if len(name) < 2 or len(name) > 120:
        return "Enter a technology name between 2 and 120 characters."
    if len(definition) < 20 or len(definition) > 1000:
        return "Add a description between 20 and 1,000 characters explaining what the technology does."
    words = re.findall(r"[A-Za-z][A-Za-z0-9+'-]*", definition.lower())
    if len(words) < 4:
        return "The description is too brief to identify a distinct technology. Explain its purpose, users, or technical approach."
    if len(set(words)) / len(words) < 0.55 or re.search(r"(.)\1{4,}", f"{name} {definition}".lower()):
        return "The name or description appears to be placeholder text rather than a technology. Use the recognised name and a plain-language explanation."
    generic = {"ai", "artificial", "intelligence", "technology", "software", "platform", "tool", "tools", "solution", "system", "app", "application", "thing", "stuff"}
    meaningful_words = [word for word in words if word not in generic]
    if len(set(meaningful_words)) < 2:
        return "The description is too broad to track. Name a distinct technology or category and explain what separates it from general AI software."
    return None


def _prompt(display_name: str, description: str) -> str:
    return f"""Prepare an editable ARGUS technology-tracking profile for an administrator.

Technology name: {display_name}
Administrator's description: {description}

First decide whether this submission identifies a real, distinct, trackable technology or technology category. Reject it when the name is gibberish, a placeholder, an ambiguous shorthand without enough context, a broad trend, a company, or an individual product release. If rejecting, set `decision` to `reject`, state the specific operator-facing reason in `reason`, and leave every field in `profile` empty (empty strings and arrays). Do not guess what the administrator meant.

Only when it is distinct and researchable, set `decision` to `ready`. Use web search to resolve factual configuration details, especially official or canonical GitHub repositories. Do not invent repository names, vendors, citations, or claims. Return a concise definition that preserves the administrator's meaning. The slug must be lowercase hyphenated. `kind` is a short category such as protocol, framework, or developer tool. Build focused Hacker News and news queries and 3-12 relevance terms. Include only public GitHub owner/repository values you are confident are correct. This is a draft proposal: an administrator must inspect and edit every field before creating it."""


def enrich_profile(display_name: object, description: object) -> dict[str, Any]:
    name = str(display_name or "").strip()
    definition = str(description or "").strip()
    issue = _input_issue(name, definition)
    if issue:
        raise ValueError(issue)
    try:
        profile, metadata = complete_json(
            prompt=_prompt(name, definition), schema_name="technology_profile_enrichment", schema=ENRICHMENT_SCHEMA, use_web_search=True,
        )
    except LLMError as error:
        raise ValueError(str(error)) from error
    decision = profile.get("decision")
    reason = str(profile.get("reason", "")).strip()
    if decision == "reject":
        raise ValueError(f"AI could not prepare this technology: {reason or 'the name and description do not identify a distinct, researchable technology.'}")
    if decision != "ready":
        raise ValueError("AI preparation returned an invalid eligibility decision")
    profile = profile.get("profile")
    if not isinstance(profile, dict):
        raise ValueError("AI preparation returned no editable technology profile")
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
