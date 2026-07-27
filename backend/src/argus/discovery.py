"""Weekly technology-candidate discovery using OpenRouter web search."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from typing import Any
from argus.llm import DEFAULT_MODEL, LLMError, complete_json


CANDIDATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "candidates": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "slug": {"type": "string"},
                    "display_name": {"type": "string"},
                    "kind": {"type": "string"},
                    "definition": {"type": "string"},
                    "rationale": {"type": "string"},
                    "emergence_score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "news_query": {"type": "string"},
                    "hn_query": {"type": "string"},
                    "github_repos": {"type": "array", "items": {"type": "string"}},
                    "relevance_terms": {"type": "array", "items": {"type": "string"}},
                    "evidence_urls": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["slug", "display_name", "kind", "definition", "rationale", "emergence_score", "news_query", "hn_query", "github_repos", "relevance_terms", "evidence_urls"],
            },
        },
    },
    "required": ["candidates"],
}


class DiscoveryError(RuntimeError):
    """A safe, operator-facing discovery failure."""


def _prompt(technologies: list[dict[str, Any]]) -> str:
    known = [
        {
            "name": item["display_name"],
            "definition": item["definition"],
            "status": item["status"],
            "analysis_cadence": item.get("analysis_cadence", "weekly"),
            "relevance_terms": item.get("relevance_terms", []),
        }
        for item in technologies
    ]
    return f"""You are the discovery analyst for ARGUS, an evidence-led technology hype and maturity tracker.

Search current, reputable web sources for AI infrastructure, protocols, developer tools, model-serving techniques, agent runtimes, evaluation methods, and interface standards that may warrant weekly lifecycle tracking.

Build a balanced candidate queue. Look for both newly emerging technologies and well-known or moderately established technologies that have active public ecosystems but are missing from ARGUS. Do not limit the search to launches, announcements, or technologies that first appeared recently. A mature household-name category is still eligible if it is distinct, currently observable, and useful to compare on the ARGUS lifecycle; a broad, untrackable trend is not.

Known or already monitored technologies (do not suggest duplicates or aliases):
{json.dumps(known, ensure_ascii=False)}

Only suggest a candidate when it is:
- a distinct technology/category rather than a company, individual product release, model version, or broad trend;
- supported by at least two recent, independent, attributable sources;
- active enough that recurring attention/adoption/maturity analysis is useful, whether it is emerging or established;
- queryable through public news, Hacker News, or GitHub metadata.

The emergence_score field is a 0-100 tracking-priority score, not a novelty score. Assess it from distinctness, current public signal, source quality, and the value of tracking the category weekly. Prefer 0-5 strong candidates over filling the list, with a mix of emerging and established gaps when justified. Use lowercase hyphenated slugs. Include only real owner/repository values you can verify. Evidence URLs must be direct source URLs. Return JSON matching the supplied schema and no prose."""


def _identity_keys(item: dict[str, Any]) -> set[str]:
    """Return conservative exact identifiers used to suppress known technologies and aliases."""
    values = [item.get("id", ""), item.get("slug", ""), item.get("display_name", "")]
    values.extend(item.get("relevance_terms", []))
    keys = set()
    for value in values:
        text = str(value).strip().lower()
        normalized = re.sub(r"[^a-z0-9]+", "", text)
        if normalized:
            keys.add(normalized)
        keys.update(
            normalized_alias
            for alias in re.findall(r"\(([^)]+)\)", text)
            if (normalized_alias := re.sub(r"[^a-z0-9]+", "", alias.lower()))
        )
    return keys


def _validate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    slug = str(candidate.get("slug", "")).strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise DiscoveryError(f"OpenRouter returned an invalid candidate slug: {slug or '(empty)'}")
    required_text = ("display_name", "kind", "definition", "rationale", "news_query", "hn_query")
    if any(not str(candidate.get(key, "")).strip() for key in required_text):
        raise DiscoveryError(f"OpenRouter returned incomplete candidate metadata for {slug}")
    score = candidate.get("emergence_score")
    if not isinstance(score, int) or not 0 <= score <= 100:
        raise DiscoveryError(f"OpenRouter returned an invalid emergence score for {slug}")
    repositories = candidate.get("github_repos", [])
    terms = candidate.get("relevance_terms", [])
    urls = candidate.get("evidence_urls", [])
    if not isinstance(repositories, list) or not repositories or any(not re.fullmatch(r"[^/\s]+/[^/\s]+", str(value)) for value in repositories):
        raise DiscoveryError(f"OpenRouter returned invalid repositories for {slug}")
    if not isinstance(terms, list) or not terms or any(not str(value).strip() for value in terms):
        raise DiscoveryError(f"OpenRouter returned invalid relevance terms for {slug}")
    if not isinstance(urls, list) or len(urls) < 2 or any(not str(value).startswith(("https://", "http://")) for value in urls):
        raise DiscoveryError(f"OpenRouter returned fewer than two valid evidence URLs for {slug}")
    return {**candidate, "slug": slug, "github_repos": repositories, "relevance_terms": terms, "evidence_urls": urls}


def discover(technologies: list[dict[str, Any]], api_key: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Return validated, web-grounded candidates. The caller persists the result."""
    try:
        output, metadata = complete_json(
            prompt=_prompt(technologies), schema_name="technology_candidates", schema=CANDIDATE_SCHEMA,
            api_key=api_key, model=model or os.environ.get("ARGUS_DISCOVERY_MODEL", DEFAULT_MODEL), use_web_search=True,
        )
    except LLMError as error:
        raise DiscoveryError(str(error)) from error
    candidates = [_validate_candidate(item) for item in output.get("candidates", [])]
    known_identities = set().union(*(_identity_keys(item) for item in technologies)) if technologies else set()
    candidates = [item for item in candidates if not (_identity_keys(item) & known_identities)]
    annotations = metadata["message"].get("annotations", [])
    if not isinstance(annotations, list):
        annotations = []
    sources = [
        {"title": item.get("url_citation", {}).get("title", ""), "url": item.get("url_citation", {}).get("url", "")}
        for item in annotations if item.get("type") == "url_citation" and item.get("url_citation", {}).get("url")
    ]
    return {
        "provider": "openrouter",
        "model": metadata["model"],
        "completed_at": datetime.now(UTC).isoformat(),
        "candidates": candidates,
        "grounding_sources": sources,
        "search_queries": [],
    }
