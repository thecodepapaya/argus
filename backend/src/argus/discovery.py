"""Weekly emerging-technology discovery using Gemini with Google Search grounding."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_MODEL = "gemini-3.6-flash"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
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
        }
        for item in technologies
    ]
    return f"""You are the discovery analyst for ARGUS, an evidence-led technology hype and maturity tracker.

Search current, reputable web sources for newly emerging AI infrastructure, protocols, developer tools, model-serving techniques, agent runtimes, evaluation methods, and interface standards that may warrant weekly lifecycle tracking.

Known or already monitored technologies (do not suggest duplicates or aliases):
{json.dumps(known, ensure_ascii=False)}

Only suggest a candidate when it is:
- a distinct technology/category rather than a company, individual product release, model version, or broad trend;
- supported by at least two recent, independent, attributable sources;
- new enough that weekly attention/adoption/maturity analysis is useful;
- queryable through public news, Hacker News, or GitHub metadata.

Prefer 0-5 strong candidates over filling the list. Use lowercase hyphenated slugs. Include only real owner/repository values you can verify. Evidence URLs must be direct source URLs. Return JSON matching the supplied schema and no prose."""


def _extract_text(response: dict[str, Any]) -> str:
    try:
        parts = response["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as error:
        reason = response.get("promptFeedback", {}).get("blockReason", "empty model response")
        raise DiscoveryError(f"Gemini returned no discovery result: {reason}") from error
    text = "".join(part.get("text", "") for part in parts)
    if not text:
        raise DiscoveryError("Gemini returned an empty discovery result")
    return text


def _validate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    slug = str(candidate.get("slug", "")).strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise DiscoveryError(f"Gemini returned an invalid candidate slug: {slug or '(empty)'}")
    required_text = ("display_name", "kind", "definition", "rationale", "news_query", "hn_query")
    if any(not str(candidate.get(key, "")).strip() for key in required_text):
        raise DiscoveryError(f"Gemini returned incomplete candidate metadata for {slug}")
    score = candidate.get("emergence_score")
    if not isinstance(score, int) or not 0 <= score <= 100:
        raise DiscoveryError(f"Gemini returned an invalid emergence score for {slug}")
    repositories = candidate.get("github_repos", [])
    terms = candidate.get("relevance_terms", [])
    urls = candidate.get("evidence_urls", [])
    if not isinstance(repositories, list) or not repositories or any(not re.fullmatch(r"[^/\s]+/[^/\s]+", str(value)) for value in repositories):
        raise DiscoveryError(f"Gemini returned invalid repositories for {slug}")
    if not isinstance(terms, list) or not terms or any(not str(value).strip() for value in terms):
        raise DiscoveryError(f"Gemini returned invalid relevance terms for {slug}")
    if not isinstance(urls, list) or len(urls) < 2 or any(not str(value).startswith(("https://", "http://")) for value in urls):
        raise DiscoveryError(f"Gemini returned fewer than two valid evidence URLs for {slug}")
    return {**candidate, "slug": slug, "github_repos": repositories, "relevance_terms": terms, "evidence_urls": urls}


def discover(technologies: list[dict[str, Any]], api_key: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Return validated, web-grounded candidates. The caller persists the result."""
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise DiscoveryError("GEMINI_API_KEY is not configured; weekly technology discovery is disabled")
    selected_model = model or os.environ.get("ARGUS_DISCOVERY_MODEL", DEFAULT_MODEL)
    endpoint = GEMINI_ENDPOINT.format(model=quote(selected_model, safe=".-"))
    payload = {
        "contents": [{"parts": [{"text": _prompt(technologies)}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": CANDIDATE_SCHEMA,
        },
    }
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key, "User-Agent": "ARGUS-discovery/0.5"},
        method="POST",
    )
    response: dict[str, Any] | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as raw:  # nosec B310: endpoint is a fixed Google HTTPS origin
                response = json.loads(raw.read().decode("utf-8"))
            break
        except HTTPError as error:
            detail = error.read(1000).decode("utf-8", errors="replace")
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise DiscoveryError(f"Gemini discovery request failed with HTTP {error.code}: {detail}") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt == 2:
                raise DiscoveryError(f"Gemini discovery request failed: {error}") from error
        time.sleep(2 ** attempt)
    if response is None:
        raise DiscoveryError("Gemini discovery request did not return a response")
    try:
        output = json.loads(_extract_text(response))
    except json.JSONDecodeError as error:
        raise DiscoveryError("Gemini discovery output was not valid JSON") from error
    candidates = [_validate_candidate(item) for item in output.get("candidates", [])]
    known_slugs = {item["id"] for item in technologies}
    candidates = [item for item in candidates if item["slug"] not in known_slugs]
    grounding = response.get("candidates", [{}])[0].get("groundingMetadata", {})
    sources = [
        {"title": chunk.get("web", {}).get("title", ""), "url": chunk.get("web", {}).get("uri", "")}
        for chunk in grounding.get("groundingChunks", [])
        if chunk.get("web", {}).get("uri")
    ]
    return {
        "provider": "google-gemini",
        "model": selected_model,
        "completed_at": datetime.now(UTC).isoformat(),
        "candidates": candidates,
        "grounding_sources": sources,
        "search_queries": grounding.get("webSearchQueries", []),
    }
