# Implemented methodology

This document describes what ARGUS 0.5 computes today. The longer [product blueprint](PLAN.md) contains future research ideas and must not be read as implemented behavior. The machine-readable contract is `GET /api/v1/methodology`.

## Inputs and collection

ARGUS retains public metadata and short feed summaries, not article bodies. The current adapters collect:

- GitHub repository metadata and weekly commit activity;
- dated Hacker News stories matching configured relevance terms;
- current Google News RSS titles, links, dates, and summaries.

GitHub collection works anonymously but uses `GITHUB_TOKEN` when configured to
avoid the low unauthenticated quota. The token does not change scoring.

Exact normalized-title duplicates are removed. ARGUS does not currently perform semantic claim clustering, full-text extraction, organization-level production verification, or LLM classification of evidence. OpenRouter is used only for separate technology-candidate discovery and administrator-requested draft-profile preparation.

## Signal dimensions

All dimensions except momentum use a 0–100 normalized scale. Momentum ranges from −100 to 100.

| Dimension | Implemented meaning |
|---|---|
| Attention | Relative public discussion and project activity; visibility, not quality |
| Expectations | Forward-looking impact or replacement language in collected metadata |
| Disappointment | Setback, limitation, security, reliability, or failure language |
| Verified adoption | A deliberately conservative public-use signal; repository activity is capped as a weak proxy and is not production proof |
| Operational maturity | Maintenance, release, governance, integration, and operating-practice signals |
| Momentum | Current activity relative to a trailing four-week baseline |
| Evidence coverage | Completeness of configured source collection, not percentage of the internet observed |

`hype_gap = expectations - adoption`. A positive result means claims are running ahead of observed use. It is not a prediction that the technology will fail.

## Evidence weights

The implemented metadata weights are 0.90 for GitHub repository evidence, 0.62 for Google News RSS evidence, and 0.48 for Hacker News evidence. These values express relative analytical influence for the associated claim type. They are not truth probabilities. Source failures reduce coverage and remain visible.

## Phase inference

The deterministic scoring model in `backend/src/argus/inference/engine.py` evaluates five qualitative phases. It combines the dimensions with explicit weights and adds only a modest continuity preference for the same or an adjacent prior phase. Softmax converts scores to a phase distribution. No LLM selects a phase.

Confidence combines source coverage and separation between the two leading phase scores, then applies conflict and coverage caps. The UI shows low, moderate, or high confidence; the numeric score is a model diagnostic, not measured accuracy.

## Lifecycle cadence

Active technologies are analyzed weekly by default. After 12 consecutive weekly snapshots spanning at least 11 weeks in `plateau_of_productivity`, ARGUS changes their analysis cadence to quarterly. They remain publicly visible, become due every 12 weeks, and can be returned to weekly analysis by an operator. The threshold is configurable with `ARGUS_PLATEAU_WEEKS`, with a safety minimum of eight weeks.

## Limitations

- Public data overrepresents English-language and open-source activity.
- Current historical signals are reconstructed from GitHub and Hacker News metadata.
- Headline keyword classification can miss context and must not be treated as semantic fact extraction.
- News RSS availability and repository APIs can be incomplete or rate-limited.
- ARGUS is independent, not affiliated with Gartner, and does not reproduce official Gartner research.
