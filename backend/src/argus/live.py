"""Real, attributable public-data collection for ARGUS.

The module intentionally stores only public metadata and short feed summaries. It
does not scrape article bodies, and its persisted result is a dated cache so the
dashboard remains useful when a public API is unavailable or rate-limited.
"""

from __future__ import annotations

import json
import os
import re
import statistics
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from argus.ingestion.rss import fetch_rss
from argus.inference.engine import infer
from argus.methodology import METHODOLOGY_VERSION


ROOT = Path(__file__).resolve().parents[3]
CACHE_PATH = ROOT / "data" / "fixtures" / "live_snapshot.json"
TECHNOLOGY_CONFIG_PATH = ROOT / "config" / "technologies"
USER_AGENT = "ARGUS/0.5 (public metadata research)"

def load_technology_configs(path: Path = TECHNOLOGY_CONFIG_PATH) -> dict[str, dict[str, Any]]:
    """Load source-controlled built-in profiles from runtime JSON configuration."""
    technologies: dict[str, dict[str, Any]] = {}
    for config_path in sorted(path.glob("*.json")):
        profile = json.loads(config_path.read_text(encoding="utf-8"))
        technology_id = profile.get("id")
        required = ("id", "display_name", "kind", "definition", "github_repos", "hn_query", "news_query", "relevance_terms")
        if any(not profile.get(key) for key in required):
            raise ValueError(f"Incomplete technology configuration: {config_path}")
        list_options = ("official_feeds", "npm_packages", "stackexchange_tags")
        if any(key in profile and (not isinstance(profile[key], list) or not all(isinstance(value, str) and value.strip() and len(value) <= 300 for value in profile[key])) for key in list_options):
            raise ValueError(f"Invalid optional source configuration: {config_path}")
        if "openalex_query" in profile and (not isinstance(profile["openalex_query"], str) or not profile["openalex_query"].strip() or len(profile["openalex_query"]) > 300):
            raise ValueError(f"Invalid OpenAlex query: {config_path}")
        if technology_id in technologies:
            raise ValueError(f"Duplicate technology configuration: {technology_id}")
        technologies[technology_id] = profile
    if not technologies:
        raise ValueError(f"No technology configurations found in {path}")
    return technologies


TECHNOLOGIES = load_technology_configs()

SOURCE_DISCLOSURE = [
    {"name": "GitHub public API", "class": "source_code_or_registry", "weight": "High for public repository activity and release metadata"},
    {"name": "Hacker News public search", "class": "community_forum", "weight": "Moderate for developer attention; not adoption proof"},
    {"name": "Google News RSS", "class": "established_technical_press", "weight": "Moderate for current attention and claims; exact duplicate titles are removed"},
]

SOURCE_METADATA = {
    "github": ("GitHub public API", "source_code_or_registry"),
    "github_releases": ("GitHub releases", "release_metadata"),
    "github_advisories": ("GitHub repository advisories", "security_advisory"),
    "hacker_news": ("Hacker News public search", "community_forum"),
    "google_news": ("Google News RSS", "established_technical_press"),
    "official_feeds": ("Official project feeds", "first_party_announcement"),
    "npm": ("npm registry", "package_registry"),
    "osv": ("OSV vulnerability database", "security_advisory"),
    "stackexchange": ("Stack Exchange public API", "developer_community"),
    "openalex": ("OpenAlex public API", "research_metadata"),
}

FEATURE_NAMES = {"attention", "expectations", "disappointment", "adoption", "maturity", "momentum", "coverage"}
PHASE_NAMES = {"innovation_trigger", "peak_of_inflated_expectations", "trough_of_disillusionment", "slope_of_enlightenment", "plateau_of_productivity"}
CALIBRATED_SOURCE_DELTAS = {
    ("release_metadata", "maturity"): 5.0,
    ("package_registry", "maturity"): 5.0,
    ("security_advisory", "disappointment"): 7.0,
    ("developer_community", "adoption"): 4.0,
    ("research_metadata", "maturity"): 3.0,
    ("first_party_announcement", "maturity"): 2.0,
}


def _get_json(url: str, accept: str = "application/vnd.github+json") -> Any:
    headers = {"Accept": accept, "User-Agent": USER_AGENT}
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {github_token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=20) as response:  # nosec B310: fixed HTTPS source URLs
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict[str, Any]) -> Any:
    """POST only to adapter-owned fixed endpoints; profiles never supply URLs."""
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:  # nosec B310: fixed HTTPS OSV endpoint
        return json.loads(response.read().decode("utf-8"))


def _week_start(value: datetime) -> str:
    day = value.date() - timedelta(days=value.weekday())
    return day.isoformat()


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def _keyword_dimension(text: str) -> tuple[str, str, str]:
    lowered = text.lower()
    if any(term in lowered for term in ("security", "vulnerab", "breach", "incident", "risk", "failure", "bug", "unsafe")):
        return "disappointment", "contradicting", "limitation"
    if any(term in lowered for term in ("production", "deploy", "customer", "enterprise", "adopt", "integration", "support")):
        return "adoption", "supporting", "adoption_signal"
    if any(term in lowered for term in ("standard", "spec", "release", "sdk", "governance", "security", "registry")):
        return "maturity", "supporting", "maturity_signal"
    if any(term in lowered for term in ("funding", "revolution", "replace", "promise", "billion", "future")):
        return "expectations", "supporting", "expectation_signal"
    return "attention", "supporting", "attention_signal"


def _is_relevant(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _github_repo(repo: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    details = _get_json(f"https://api.github.com/repos/{repo}")
    activity = _get_json(f"https://api.github.com/repos/{repo}/stats/commit_activity")
    if not isinstance(activity, list):
        activity = []
    return details, activity


def _github_releases(repo: str) -> list[dict[str, Any]]:
    payload = _get_json(f"https://api.github.com/repos/{repo}/releases?per_page=5")
    return payload if isinstance(payload, list) else []


def _github_advisories(repo: str) -> list[dict[str, Any]]:
    payload = _get_json(f"https://api.github.com/repos/{repo}/security-advisories?per_page=10")
    return payload if isinstance(payload, list) else []


def _hn_stories(query: str, after: datetime) -> list[dict[str, Any]]:
    params = urlencode({"query": query, "tags": "story", "hitsPerPage": 100, "numericFilters": f"created_at_i>{int(after.timestamp())}"})
    payload = _get_json(f"https://hn.algolia.com/api/v1/search_by_date?{params}", "application/json")
    return payload.get("hits", []) if isinstance(payload, dict) else []


def _news_items(query: str) -> list[dict[str, Any]]:
    url = "https://news.google.com/rss/search?" + urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return fetch_rss(url, "Google News RSS", limit=18)


def _official_feed_items(feeds: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for url in feeds:
        records.extend(fetch_rss(url, "Official project feed", limit=12))
    return records


def _npm_package(name: str) -> dict[str, Any]:
    return _get_json(f"https://registry.npmjs.org/{quote(name, safe='@/')}", "application/json")


def _osv_advisories(package: str) -> list[dict[str, Any]]:
    payload = _post_json("https://api.osv.dev/v1/query", {"package": {"ecosystem": "npm", "name": package}})
    return payload.get("vulns", []) if isinstance(payload, dict) else []


def _stackexchange_questions(tags: list[str], after: datetime) -> list[dict[str, Any]]:
    if not tags:
        return []
    params = urlencode({"site": "stackoverflow", "tagged": ";".join(tags), "pagesize": 30, "fromdate": int(after.timestamp()), "order": "desc", "sort": "creation"})
    payload = _get_json(f"https://api.stackexchange.com/2.3/questions?{params}", "application/json")
    return payload.get("items", []) if isinstance(payload, dict) else []


def _openalex_works(query: str) -> list[dict[str, Any]]:
    if not query:
        return []
    payload = _get_json("https://api.openalex.org/works?" + urlencode({"search": query, "per-page": 15}), "application/json")
    return payload.get("results", []) if isinstance(payload, dict) else []


def _repo_evidence(repo: dict[str, Any], tech_id: str, current_week: str) -> dict[str, Any]:
    pushed = repo.get("pushed_at") or repo.get("updated_at") or datetime.now(UTC).isoformat()
    description = repo.get("description") or "Public repository metadata collected from GitHub."
    stars = int(repo.get("stargazers_count", 0))
    forks = int(repo.get("forks_count", 0))
    return {
        "id": f"github:{tech_id}:{repo['full_name']}", "week": current_week, "dimension": "maturity", "stance": "supporting",
        "claim_type": "repository_activity", "source": "GitHub public API", "source_class": "source_code_or_registry", "first_party": False,
        "weight": 0.9, "date": pushed[:10], "title": f"{repo['full_name']}: {stars:,} stars · {forks:,} forks",
        "excerpt": description, "url": repo["html_url"], "status": "attributed_public_metadata",
    }


def _hn_evidence(story: dict[str, Any], tech_id: str, current_week: str) -> dict[str, Any] | None:
    title = story.get("title") or story.get("story_title")
    if not title:
        return None
    dimension, stance, claim_type = _keyword_dimension(title)
    story_url = story.get("url") or story.get("story_url") or f"https://news.ycombinator.com/item?id={story.get('objectID')}"
    created = story.get("created_at", "")
    return {
        "id": f"hn:{tech_id}:{story.get('objectID')}", "week": current_week, "dimension": dimension, "stance": stance,
        "claim_type": claim_type, "source": "Hacker News", "source_class": "community_forum", "first_party": False,
        "weight": 0.48, "date": created[:10], "title": title,
        "excerpt": f"Developer-community discussion with {int(story.get('points') or 0):,} points and {int(story.get('num_comments') or 0):,} comments.",
        "url": story_url, "status": "attributed_public_metadata",
    }


def _news_evidence(item: dict[str, Any], tech_id: str, current_week: str) -> dict[str, Any]:
    dimension, stance, claim_type = _keyword_dimension(f"{item['title']} {item.get('excerpt', '')}")
    return {
        "id": f"news:{tech_id}:{item['url']}", "week": current_week, "dimension": dimension, "stance": stance,
        "claim_type": claim_type, "source": "Google News RSS", "source_class": "established_technical_press", "first_party": False,
        "weight": 0.62, "date": item["published_at"][:10], "title": item["title"],
        "excerpt": item.get("excerpt") or "Headline collected from a current Google News RSS search.", "url": item["url"],
        "status": "attributed_public_metadata",
    }


def _external_evidence(source_key: str, item: dict[str, Any], tech_id: str, current_week: str) -> dict[str, Any] | None:
    """Normalize metadata-only records from optional, attributable source families."""
    source, source_class = SOURCE_METADATA[source_key]
    if source_key == "npm":
        name = item.get("name")
        if not name:
            return None
        modified = item.get("time", {}).get("modified", "")
        return {"id": f"npm:{tech_id}:{name}", "week": current_week, "dimension": "maturity", "stance": "supporting", "claim_type": "package_registry_metadata", "source": source, "source_class": source_class, "first_party": False, "weight": 0.7, "date": modified[:10], "title": f"{name}: package registry metadata", "excerpt": item.get("description") or "Public npm package metadata.", "url": f"https://www.npmjs.com/package/{name}", "status": "attributed_public_metadata"}
    if source_key == "osv":
        identifier = item.get("id")
        if not identifier:
            return None
        published = item.get("published", "")
        summary = item.get("summary") or item.get("details") or "Published vulnerability advisory."
        return {"id": f"osv:{tech_id}:{identifier}", "week": current_week, "dimension": "disappointment", "stance": "contradicting", "claim_type": "security_advisory", "source": source, "source_class": source_class, "first_party": False, "weight": 0.86, "date": published[:10], "title": f"{identifier}: {summary[:140]}", "excerpt": summary[:500], "url": f"https://osv.dev/vulnerability/{identifier}", "status": "attributed_public_metadata"}
    if source_key == "stackexchange":
        title, link = item.get("title"), item.get("link")
        if not title or not link:
            return None
        created = datetime.fromtimestamp(item.get("creation_date", 0), UTC).date().isoformat()
        return {"id": f"stackexchange:{tech_id}:{item.get('question_id')}", "week": current_week, "dimension": "adoption", "stance": "supporting", "claim_type": "implementation_discussion", "source": source, "source_class": source_class, "first_party": False, "weight": 0.54, "date": created, "title": title, "excerpt": f"Public developer question with {item.get('answer_count', 0)} answers.", "url": link, "status": "attributed_public_metadata"}
    if source_key == "openalex":
        title = item.get("display_name")
        identifier = item.get("id")
        if not title or not identifier:
            return None
        return {"id": f"openalex:{tech_id}:{identifier.rsplit('/', 1)[-1]}", "week": current_week, "dimension": "maturity", "stance": "supporting", "claim_type": "research_metadata", "source": source, "source_class": source_class, "first_party": False, "weight": 0.58, "date": str(item.get("publication_date") or ""), "title": title, "excerpt": "Public research metadata indexed by OpenAlex.", "url": item.get("doi") or identifier, "status": "attributed_public_metadata"}
    if source_key == "official_feeds":
        return {**_news_evidence(item, tech_id, current_week), "id": f"official:{tech_id}:{item['url']}", "source": source, "source_class": source_class, "first_party": True, "weight": 0.82, "claim_type": "official_announcement"}
    if source_key == "github_releases":
        url, name = item.get("html_url"), item.get("name") or item.get("tag_name")
        if not url or not name:
            return None
        return {"id": f"github-release:{tech_id}:{url}", "week": current_week, "dimension": "maturity", "stance": "supporting", "claim_type": "release_metadata", "source": source, "source_class": source_class, "first_party": True, "weight": 0.82, "date": str(item.get("published_at") or "")[:10], "title": name, "excerpt": (item.get("body") or "Public GitHub release metadata.")[:500], "url": url, "status": "attributed_public_metadata"}
    if source_key == "github_advisories":
        url, identifier = item.get("html_url"), item.get("ghsa_id") or item.get("cve_id")
        if not url or not identifier:
            return None
        return {"id": f"github-advisory:{tech_id}:{identifier}", "week": current_week, "dimension": "disappointment", "stance": "contradicting", "claim_type": "security_advisory", "source": source, "source_class": source_class, "first_party": True, "weight": 0.86, "date": str(item.get("published_at") or "")[:10], "title": f"{identifier}: {item.get('summary') or 'Repository security advisory'}", "excerpt": (item.get("description") or "Public GitHub security advisory.")[:500], "url": url, "status": "attributed_public_metadata"}
    return None


def _deduplicate_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove repeated title-level signals while retaining the strongest source."""
    selected: dict[str, dict[str, Any]] = {}
    for item in items:
        key = re.sub(r"[^a-z0-9]+", " ", item["title"].lower()).strip()
        existing = selected.get(key)
        if existing is None or item["weight"] > existing["weight"]:
            selected[key] = item
    return list(selected.values())


def _history(repo_activities: list[list[dict[str, Any]]], stories: list[dict[str, Any]], current: datetime) -> list[dict[str, Any]]:
    story_by_week: dict[str, list[dict[str, Any]]] = {}
    for story in stories:
        try:
            created = datetime.fromisoformat(story["created_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        story_by_week.setdefault(_week_start(created), []).append(story)
    commits_by_week: dict[str, int] = {}
    for activities in repo_activities:
        for row in activities:
            if not row.get("week"):
                continue
            week = _week_start(datetime.fromtimestamp(row["week"], UTC))
            commits_by_week[week] = commits_by_week.get(week, 0) + int(row.get("total", 0))
    weeks = [_week_start(current - timedelta(weeks=offset)) for offset in range(51, -1, -1)]
    commit_values = [commits_by_week.get(week, 0) for week in weeks]
    discussion_values = [len(story_by_week.get(week, [])) for week in weeks]
    snapshots: list[dict[str, Any]] = []
    previous_phase = None
    for index, week in enumerate(weeks):
        discussions = story_by_week.get(week, [])
        commits = commits_by_week.get(week, 0)
        # Normalize only against information available at this point in time. A
        # later spike must not rewrite earlier lifecycle estimates downward.
        max_commits_to_date = max(commit_values[:index + 1]) or 1
        max_discussions_to_date = max(discussion_values[:index + 1]) or 1
        attention = _clamp(18 + 75 * discussion_values[index] / max_discussions_to_date)
        expectations = _clamp(15 + 55 * sum(_keyword_dimension((story.get("title") or ""))[0] == "expectations" for story in discussions) / max(1, len(discussions)) + attention * 0.22)
        disappointment = _clamp(8 + 65 * sum(_keyword_dimension((story.get("title") or ""))[0] == "disappointment" for story in discussions) / max(1, len(discussions)))
        # Public repository activity is a weak adoption proxy. Keep it bounded so
        # code activity cannot be mistaken for independently verified production use.
        adoption = _clamp(8 + 24 * commits / max_commits_to_date)
        maturity = _clamp(24 + 70 * commits / max_commits_to_date)
        prior = commit_values[max(0, index - 4):index] or [0]
        settling = index == len(weeks) - 1
        momentum = 0 if settling else _clamp(50 + (commits - statistics.mean(prior)) * 1.8) - 50
        coverage = _clamp(42 + (30 if commits else 0) + min(28, len(discussions) * 5))
        features = {"attention": attention, "expectations": expectations, "disappointment": disappointment, "adoption": adoption, "maturity": maturity, "momentum": momentum, "momentum_available": not settling, "coverage": coverage}
        estimate = infer(features, previous_phase)
        previous_phase = estimate["phase"]
        snapshots.append({"week": week, "features": features, **estimate, "model_version": METHODOLOGY_VERSION, "period_status": "settling" if settling else "closed", "coverage_warning": None if coverage >= 65 else "Partial historical coverage: public commit activity and dated developer discussion only."})
    return snapshots


def _apply_current_repository_signal(snapshots: list[dict[str, Any]], repositories: list[dict[str, Any]], current: datetime, calibration: dict[str, float] | None = None) -> None:
    """Use actual repository recency when GitHub's weekly aggregates lag the current week."""
    active_repositories = 0
    for repository in repositories:
        value = repository.get("pushed_at") or repository.get("updated_at")
        if not value:
            continue
        try:
            pushed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if pushed >= current - timedelta(days=28):
            active_repositories += 1
    if not snapshots or not active_repositories:
        return
    snapshot = snapshots[-1]
    features = snapshot["features"]
    features["adoption"] = _clamp(max(features["adoption"], 10 + active_repositories * 7))
    features["maturity"] = _clamp(max(features["maturity"], 25 + active_repositories * 14))
    # Some categories have abundant open-source tooling but sparse independently
    # verified deployment evidence. Per-category calibration is versioned with the
    # technology profile so repository popularity is not mislabeled as adoption.
    calibration = calibration or {}
    features["attention"] = _clamp(max(features["attention"], calibration.get("attention_floor", 0)))
    features["expectations"] = _clamp(max(features["expectations"], calibration.get("expectations_floor", 0)))
    if "adoption_cap" in calibration:
        features["adoption"] = _clamp(min(features["adoption"], calibration["adoption_cap"]))
    previous_phase = snapshots[-2]["phase"] if len(snapshots) > 1 else None
    snapshot.update(infer(features, previous_phase))


def _source_coverage(source_health: dict[str, bool]) -> float:
    """Return collection completeness from adapter outcomes, never activity volume."""
    applicable = list(source_health.values())
    return _clamp(100 * sum(applicable) / len(applicable)) if applicable else 0


def _apply_source_calibration(snapshots: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
    """Apply bounded, source-class-specific current-week adjustments.

    Each source class can contribute at most once per feature. This prevents a
    release flood, advisory list, or syndicated announcement from dominating an
    estimate while making the calibration traceable in the resulting snapshot.
    """
    if not snapshots:
        return
    features = snapshots[-1]["features"]
    applied: set[tuple[str, str]] = set()
    independent_classes = {item.get("source_class") for item in evidence if item.get("source_class")}
    adoption_classes = {item.get("source_class") for item in evidence if item.get("dimension") == "adoption" and item.get("source_class") not in {"source_code_or_registry", "first_party_announcement"}}
    for item in evidence:
        key = (item.get("source_class"), item.get("dimension"))
        delta = CALIBRATED_SOURCE_DELTAS.get(key)
        if not delta or key in applied:
            continue
        features[key[1]] = _clamp(features[key[1]] + delta * min(1.0, float(item.get("weight", 0))))
        applied.add(key)
    features["independent_sources"] = len(independent_classes)
    features["independent_adoption_sources"] = len(adoption_classes)
    snapshots[-1]["calibration_trace"] = [{"source_class": source_class, "feature": feature, "delta_cap": delta} for (source_class, feature), delta in CALIBRATED_SOURCE_DELTAS.items() if (source_class, feature) in applied]
    previous_phase = snapshots[-2]["phase"] if len(snapshots) > 1 else None
    snapshots[-1].update(infer(features, previous_phase))


def collect_technology(technology: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Collect a configuration-driven technology profile using existing adapters."""
    now = now or datetime.now(UTC)
    current_week = _week_start(now)
    tech_id = technology["id"]
    errors: list[str] = []
    repo_details: list[dict[str, Any]] = []
    activities: list[list[dict[str, Any]]] = []
    github_ok = True
    for repo_name in technology["github_repos"]:
        try:
            details, activity = _github_repo(repo_name)
            repo_details.append(details); activities.append(activity)
        except Exception as error:
            github_ok = False
            errors.append(f"GitHub {repo_name}: {error}")
    after = now - timedelta(weeks=53)
    try:
        stories = _hn_stories(technology["hn_query"], after)
        stories = [story for story in stories if _is_relevant(story.get("title") or story.get("story_title") or "", tuple(technology["relevance_terms"]))]
    except Exception as error:
        stories = []; errors.append(f"Hacker News: {error}"); hn_ok = False
    else:
        hn_ok = True
    try:
        news = _news_items(technology["news_query"])
        news = [item for item in news if _is_relevant(f"{item['title']} {item.get('excerpt', '')}", tuple(technology["relevance_terms"]))]
    except Exception as error:
        news = []; errors.append(f"Google News RSS: {error}"); news_ok = False
    else:
        news_ok = True
    optional_records: dict[str, list[dict[str, Any]]] = {}
    optional_health: dict[str, bool] = {}
    optional_sources = {
        "github_releases": technology["github_repos"],
        "github_advisories": technology["github_repos"],
        "official_feeds": technology.get("official_feeds", []),
        "npm": technology.get("npm_packages", []),
        "stackexchange": technology.get("stackexchange_tags", []),
        "openalex": technology.get("openalex_query", ""),
    }
    try:
        optional_records["github_releases"] = [release for repo in optional_sources["github_releases"] for release in _github_releases(repo)]
        optional_health["github_releases"] = True
    except Exception as error:
        optional_records["github_releases"] = []; optional_health["github_releases"] = False; errors.append(f"GitHub releases: {error}")
    try:
        optional_records["github_advisories"] = [advisory for repo in optional_sources["github_advisories"] for advisory in _github_advisories(repo)]
        optional_health["github_advisories"] = True
    except Exception as error:
        optional_records["github_advisories"] = []; optional_health["github_advisories"] = False; errors.append(f"GitHub repository advisories: {error}")
    if optional_sources["official_feeds"]:
        try:
            optional_records["official_feeds"] = _official_feed_items(optional_sources["official_feeds"])
            optional_health["official_feeds"] = True
        except Exception as error:
            optional_records["official_feeds"] = []; optional_health["official_feeds"] = False; errors.append(f"Official project feeds: {error}")
    if optional_sources["npm"]:
        try:
            packages = [_npm_package(package) for package in optional_sources["npm"]]
            optional_records["npm"] = packages
            optional_health["npm"] = True
            try:
                optional_records["osv"] = [advisory for package in optional_sources["npm"] for advisory in _osv_advisories(package)]
                optional_health["osv"] = True
            except Exception as error:
                optional_records["osv"] = []; optional_health["osv"] = False; errors.append(f"OSV vulnerability database: {error}")
        except Exception as error:
            optional_records["npm"] = []; optional_health["npm"] = False; errors.append(f"npm registry: {error}")
    if optional_sources["stackexchange"]:
        try:
            optional_records["stackexchange"] = _stackexchange_questions(optional_sources["stackexchange"], after)
            optional_health["stackexchange"] = True
        except Exception as error:
            optional_records["stackexchange"] = []; optional_health["stackexchange"] = False; errors.append(f"Stack Exchange public API: {error}")
    if optional_sources["openalex"]:
        try:
            optional_records["openalex"] = _openalex_works(optional_sources["openalex"])
            optional_health["openalex"] = True
        except Exception as error:
            optional_records["openalex"] = []; optional_health["openalex"] = False; errors.append(f"OpenAlex public API: {error}")
    evidence = [*(_repo_evidence(repo, tech_id, current_week) for repo in repo_details)]
    evidence.extend(item for item in (_hn_evidence(story, tech_id, current_week) for story in stories[:12]) if item)
    evidence.extend(_news_evidence(item, tech_id, current_week) for item in news[:12])
    for source_key, records in optional_records.items():
        evidence.extend(item for item in (_external_evidence(source_key, record, tech_id, current_week) for record in records[:12]) if item)
    evidence = _deduplicate_evidence(evidence)
    source_health = {"github": github_ok, "hacker_news": hn_ok, "google_news": news_ok, **optional_health}
    snapshots = _history(activities, stories, now)
    snapshots[-1]["features"]["coverage"] = _source_coverage(source_health)
    snapshots[-1]["coverage_warning"] = None if all(source_health.values()) else "Partial collection: one or more configured source families did not complete."
    _apply_current_repository_signal(snapshots, repo_details, now, technology.get("signal_calibration"))
    _apply_source_calibration(snapshots, evidence)
    return {"technology": technology, "snapshots": snapshots, "evidence": evidence, "source_errors": errors, "source_counts": {"github_repositories": len(repo_details), "hacker_news_stories": len(stories), "news_items": len(news), **{f"{key}_items": len(records) for key, records in optional_records.items()}}, "source_health": source_health}


def collect_live_data(now: datetime | None = None) -> dict[str, Any]:
    """Collect current public metadata for all built-in profiles."""
    now = now or datetime.now(UTC)
    output: dict[str, Any] = {"generated_at": now.isoformat(), "technologies": {}, "sources": SOURCE_DISCLOSURE}
    for tech_id, technology in TECHNOLOGIES.items():
        output["technologies"][tech_id] = collect_technology(technology, now)
    return output


def write_live_cache(data: dict[str, Any]) -> None:
    validate_live_data(data)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validate_live_data(data: dict[str, Any]) -> dict[str, Any]:
    """Reject incomplete or incoherent collection output before it reaches the UI."""
    if not isinstance(data, dict) or not isinstance(data.get("technologies"), dict):
        raise ValueError("Live data must contain a technologies object")
    for technology_id, profile in data["technologies"].items():
        technology = profile.get("technology", {})
        if technology.get("id") != technology_id or not technology.get("display_name") or not technology.get("definition"):
            raise ValueError(f"Invalid technology metadata for {technology_id}")
        snapshots = profile.get("snapshots")
        if not isinstance(snapshots, list) or not snapshots:
            raise ValueError(f"No snapshots available for {technology_id}")
        weeks = [snapshot.get("week") for snapshot in snapshots]
        if any(not week for week in weeks) or weeks != sorted(set(weeks)):
            raise ValueError(f"Snapshot weeks are missing, duplicated, or unordered for {technology_id}")
        for snapshot in snapshots:
            features = snapshot.get("features", {})
            if not FEATURE_NAMES.issubset(features) or snapshot.get("phase") not in PHASE_NAMES:
                raise ValueError(f"Snapshot schema is incomplete for {technology_id} at {snapshot.get('week')}")
            for name in FEATURE_NAMES:
                value = features[name]
                lower = -100 if name == "momentum" else 0
                if not isinstance(value, (int, float)) or not lower <= value <= 100:
                    raise ValueError(f"Invalid {name} value for {technology_id} at {snapshot.get('week')}")
            if "momentum_available" in features and not isinstance(features["momentum_available"], bool):
                raise ValueError(f"Invalid momentum availability for {technology_id} at {snapshot.get('week')}")
        evidence = profile.get("evidence")
        if not isinstance(evidence, list):
            raise ValueError(f"Evidence must be a list for {technology_id}")
        for item in evidence:
            if not all(item.get(key) for key in ("id", "title", "source", "url", "dimension")):
                raise ValueError(f"Evidence schema is incomplete for {technology_id}")
    return data


def _reconcile_cached_coverage(data: dict[str, Any]) -> dict[str, Any]:
    """Upgrade older cached snapshots to the current conservative signal policy."""
    for profile in data.get("technologies", {}).values():
        snapshots = profile.get("snapshots", [])
        if not snapshots:
            continue
        errors = profile.get("source_errors", [])
        source_health = {
            "github": not any(value.startswith("GitHub") for value in errors),
            "hacker_news": not any(value.startswith("Hacker News") for value in errors),
            "google_news": not any(value.startswith("Google News RSS") for value in errors),
        }
        previous_phase = None
        evidence = profile.get("evidence", [])
        for index, snapshot in enumerate(snapshots):
            features = snapshot["features"]
            # v1/v2 derived adoption primarily from commit volume. v3 caps that
            # proxy so it cannot present open-source activity as production proof.
            if snapshot.get("model_version") != METHODOLOGY_VERSION:
                features["adoption"] = _clamp(min(features["adoption"], 45))
            if index == len(snapshots) - 1:
                features["coverage"] = _source_coverage(source_health)
                features["momentum_available"] = False
                snapshot["period_status"] = "settling"
                snapshot["coverage_warning"] = None if all(source_health.values()) else "Partial collection: one or more configured source families did not complete."
                classes = {item.get("source_class") for item in evidence if item.get("source_class")}
                adoption_classes = {item.get("source_class") for item in evidence if item.get("dimension") == "adoption" and item.get("source_class") not in {"source_code_or_registry", "first_party_announcement"}}
                features["independent_sources"] = len(classes)
                features["independent_adoption_sources"] = len(adoption_classes)
            snapshot.update(infer(features, previous_phase))
            snapshot["model_version"] = METHODOLOGY_VERSION
            previous_phase = snapshot["phase"]
    return data


def load_live_cache() -> dict[str, Any] | None:
    if not CACHE_PATH.exists():
        return None
    return validate_live_data(_reconcile_cached_coverage(json.loads(CACHE_PATH.read_text(encoding="utf-8"))))
