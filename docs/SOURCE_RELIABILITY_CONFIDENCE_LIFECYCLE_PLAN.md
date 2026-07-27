# Source, confidence, and lifecycle resilience plan

Status: proposed  
Scope: data collection, evidence quality, confidence explanations, and retirement of technologies that fizzle out  
Related documents: [implemented methodology](METHODOLOGY.md), [operations runbook](runbooks/OPERATIONS.md), [technology discovery](DISCOVERY.md)

## 1. Outcome

ARGUS should make a stronger claim than “three public feeds produced a score.” It should be able to show:

1. which independent source families were checked;
2. which sources succeeded, failed, or were stale;
3. which claims were corroborated across genuinely independent sources;
4. why a lifecycle estimate has low, moderate, or high confidence;
5. what evidence would increase confidence;
6. when a technology has stopped developing into a durable category; and
7. why ARGUS stopped checking it weekly without deleting its history.

The work should retain ARGUS's current principles:

- lifecycle inference remains deterministic and versioned;
- LLMs do not assign lifecycle phases or confidence;
- public claims remain traceable to sources;
- repository popularity is not treated as production adoption;
- failures and gaps lower confidence instead of being silently ignored;
- a technology is never deleted merely because it stops being fashionable.

## 2. Current baseline

ARGUS currently collects:

| Source | Current use | Principal limitation |
| --- | --- | --- |
| GitHub public API | Repository metadata and commit activity | Strongly overrepresents open-source activity; not proof of production use |
| Hacker News search | Developer attention and dated discussion | Narrow community; discussion is not adoption |
| Google News RSS | Current headlines and summaries | Search results can be noisy, duplicated, incomplete, or unavailable |

Current confidence combines source coverage, separation between the two leading phase scores, and a conflict penalty. Coverage caps confidence, which is directionally correct, but the model cannot yet explain whether confidence is low because of source failures, stale evidence, query ambiguity, missing adoption evidence, closely competing phases, or a short history.

Current tracking cadence supports weekly and quarterly analysis. A sustained Plateau of Productivity moves to quarterly analysis, but there is no explicit outcome for technologies that lose activity before reaching durable adoption.

## 3. Design decisions

### 3.1 Separate four concepts

ARGUS should not compress these into one number:

| Concept | Question answered |
| --- | --- |
| Coverage | Did the configured collectors return usable data? |
| Evidence quality | Are the sources fresh, attributable, relevant, and independent? |
| Estimate certainty | Does one lifecycle phase clearly outrank the alternatives? |
| Technology vitality | Is the category still developing, operating, or attracting sustained use? |

The public confidence score can remain a summary, but its calculation and explanation must preserve these components.

### 3.2 Weight claims, not websites in the abstract

A source can be strong for one claim and weak for another. For example:

- an official release note is strong maturity evidence but weak independent adoption evidence;
- a package registry is useful for usage direction but cannot identify production value;
- a customer case study proves a named use occurred but remains a first-party claim;
- an independent postmortem is strong disappointment evidence;
- a news headline is attention evidence unless its underlying claim is independently supported.

Weights should therefore be a function of `source_class × claim_type × independence × freshness`, rather than one fixed weight per website.

### 3.3 Retirement is an outcome outside the five-stage curve

“Fizzled out” must not be represented as a forced move through the Trough, Slope, or Plateau. It is a tracking outcome, not a sixth lifecycle phase.

ARGUS should preserve the final lifecycle estimate and add an outcome such as:

- `fizzled_out` — activity and adoption failed to become durable;
- `superseded` — another technology or standard absorbed its role;
- `merged_into_parent_category` — evidence is no longer separable from a broader category;
- `insufficient_distinct_signal` — the term cannot be tracked reliably;
- `tracking_ended_by_operator` — explicit administrative decision.

## 4. Source expansion

### 4.1 Source priorities

Add sources in tiers. Each tier should deliver an independently useful signal before the next tier begins.

#### Tier 1 — high-value, low-cost public sources

1. **Official project feeds and changelogs**
   - RSS/Atom feeds from official blogs and release pages.
   - GitHub releases, tags, release cadence, contributor breadth, archived status, and security advisories.
   - Standards-body specifications and version history where applicable.
   - Strong for maturity, momentum, deprecation, and abandonment; mark as first-party.

2. **Package and artifact registries**
   - npm downloads and release history.
   - PyPI release history and download telemetry where a permitted public dataset is available.
   - crates.io, Maven Central, NuGet, Docker Hub, or Hugging Face only when relevant to a technology profile.
   - Useful for ecosystem activity and directional adoption proxies; never label downloads as verified production deployment.

3. **Direct technical-publication feeds**
   - Maintain an explicit allowlist of attributable technical press and practitioner publications with RSS/Atom feeds.
   - Retain publisher identity rather than treating every item as “Google News.”
   - Google News RSS remains a discovery/index layer, not the canonical publisher identity.

4. **Security and operational evidence**
   - GitHub Security Advisories, OSV, and relevant CVE metadata.
   - Official incident reports and independent postmortems.
   - Strong for disappointment and operational maturity when properly attributed.

#### Tier 2 — independent adoption and practitioner signals

5. **Stack Exchange / Stack Overflow**
   - Question volume, accepted-answer rate, unresolved-question ratio, and tag trajectory through the public API.
   - Useful for developer adoption and operating difficulty.

6. **Research and technical literature**
   - OpenAlex, Crossref, arXiv, and standards references.
   - Citation counts are lagging indicators; use publication and reference trajectories rather than raw counts alone.
   - Useful for technical legitimacy and sustained research attention, not commercial adoption.

7. **Public implementation and case-study evidence**
   - Named architecture posts, engineering blogs, conference talks with transcripts/metadata, and public customer case studies.
   - Distinguish independent implementation reports from vendor-authored case studies.
   - Require a named organization and a concrete use claim before it contributes to verified adoption.

8. **Additional developer communities**
   - Reddit only through supported API access and with community-level disclosure.
   - DEV Community, Lobsters, or other sources only after relevance and spam-rate evaluation.
   - Keep influence capped; these sources principally describe attention and practitioner friction.

#### Tier 3 — valuable but higher-cost or policy-sensitive sources

9. **Job-posting demand**
   - Use only a licensed API or dataset with clear redistribution terms.
   - Measure demand direction and skill requirements; deduplicate staffing-agency reposts.

10. **Commercial and procurement signals**
    - Public earnings-call mentions, public tenders, marketplace integrations, and partner directories.
    - Treat vendor directories as first-party unless independently confirmed.

11. **Survey datasets**
    - Import reputable recurring surveys with explicit year, sample, question wording, and methodology.
    - Do not combine incomparable survey percentages as if they share a denominator.

Paid sources should remain optional adapters. The base product must continue to run with public sources.

### 4.2 Profile-driven source configuration

Technology profiles should declare source applicability instead of every adapter running for every technology.

Proposed profile shape:

```json
{
  "sources": {
    "github": {"repositories": ["owner/repository"]},
    "official_feeds": [{"name": "Project blog", "url": "https://example.com/feed.xml"}],
    "packages": [{"registry": "npm", "name": "example-package"}],
    "stack_exchange": {"tags": ["example-tag"]},
    "research": {"queries": ["example technology"]},
    "security": {"ecosystems": ["PyPI"], "packages": ["example-package"]}
  }
}
```

Admin-created profiles should be able to add and validate these sources without code changes. Each adapter needs a `validate configuration` operation before a profile can be published.

### 4.3 Normalized evidence contract

Every adapter should emit a common envelope:

```text
EvidenceEnvelope
├── source_id / source_class / publisher
├── technology_id
├── observed_at / published_at
├── canonical_url / external_id / content_hash
├── title / permitted_excerpt
├── claim_type / dimension / stance
├── first_party / independence_group
├── source_weight / claim_weight / freshness_weight
├── relevance_score / ambiguity_flags
├── collection_run_id / adapter_version
└── licensing_and_retention_policy
```

The stored weight must be reproducible from versioned policy. A collector must not supply an unexplained final weight.

### 4.4 Independence and corroboration

Confidence must not increase merely because many sites repeat the same announcement.

Add:

- canonical URL resolution;
- normalized-title deduplication;
- event/claim clustering across similar titles and URLs;
- publisher ownership groups;
- first-party versus independent classification;
- syndicated-wire and press-release detection;
- one effective vote per independence group for the same claim.

The first implementation can use deterministic URL, title, publisher, and time-window rules. Semantic clustering can later be evaluated as a separate, reviewable enrichment step.

## 5. Collection reliability

### 5.1 Adapter contract

Create a small adapter interface with:

```text
validate(profile) -> validation result
collect(profile, window, cursor) -> envelopes + next cursor
health() -> configuration and dependency status
backfill(profile, start, end) -> envelopes
```

Each adapter should declare:

- source class and supported claim types;
- authentication requirements;
- rate-limit behavior;
- maximum backfill window;
- expected freshness;
- retention constraints;
- whether the result is first-party or independent.

### 5.2 Failure handling

Implement consistent behavior across adapters:

- bounded retries with exponential backoff and jitter;
- explicit timeouts;
- per-source rate limiting;
- `ETag` and `If-Modified-Since` support where available;
- cursors/checkpoints for resumable backfills;
- a circuit breaker after repeated dependency failures;
- quarantining malformed records instead of failing an entire technology run;
- idempotent writes keyed by source, external ID, and observation window;
- replay commands for one source, technology, run, or date range;
- last-known-good public snapshots when collection is partial.

Partial success should produce a published estimate only when minimum evidence gates pass. Otherwise, retain the previous public estimate and record the new run as `insufficient_evidence`.

### 5.3 Source health data

Extend source status beyond `last_success_at` and `last_error`:

| Field | Purpose |
| --- | --- |
| `last_attempt_at` | Distinguish an idle source from a failed source |
| `last_success_at` | Measure freshness |
| `consecutive_failures` | Drive circuit breaking and alerts |
| `records_received` / `records_accepted` / `records_quarantined` | Detect schema drift and noisy queries |
| `latency_ms` | Detect slow dependencies |
| `rate_limit_remaining` | Explain throttling |
| `freshness_status` | `fresh`, `late`, `stale`, or `unknown` |
| `adapter_version` | Reproduce collection behavior |
| `error_code` and `error_detail` | Make failures actionable |

### 5.4 Operational objectives

Initial service-level objectives:

- 99% availability for already-published public pages, independent of live source availability;
- at least 95% of scheduled technology runs complete or publish an explicit partial outcome within the weekly window;
- no source error can erase a last-known-good snapshot;
- every failed source exposes an error code, timestamp, retry state, and affected technology;
- replaying a run produces no duplicate evidence;
- stale-source alerts fire before the next scheduled analysis window.

## 6. Confidence model and explanations

### 6.1 Confidence components

Replace the current mostly aggregate calculation with a versioned breakdown:

```text
confidence_score
├── collection_completeness
├── source_breadth
├── evidence_freshness
├── source_independence
├── claim_corroboration
├── dimension_completeness
├── historical_depth
├── query_specificity
└── phase_separation
    minus conflict and instability penalties
```

Recommended first-pass influence:

| Component | Intended role |
| --- | --- |
| Collection completeness | Were applicable configured sources successfully checked? |
| Source breadth | Are multiple source classes represented? |
| Freshness | Is evidence recent enough for the source's expected cadence? |
| Independence | Do signals come from distinct publishers/communities rather than repetition? |
| Corroboration | Do independent sources support material adoption, maturity, or disappointment claims? |
| Dimension completeness | Are attention, expectations, adoption, maturity, and negative evidence observable? |
| Historical depth | Is there enough consistent history to infer direction? |
| Query specificity | Is the technology name distinct enough to avoid unrelated matches? |
| Phase separation | Does one phase materially outrank alternatives? |
| Conflict / instability | Are strong signals contradictory, or does the phase change under small input variation? |

Do not let raw evidence volume dominate. Ten copies of one press release should contribute less confidence than two independent implementation reports.

### 6.2 Confidence gates

Use hard caps to prevent misleading confidence:

- no `high` confidence without at least three applicable source classes;
- no `high` confidence without at least one independent source supporting adoption or maturity;
- cap confidence when evidence is predominantly first-party;
- cap confidence when a required source is stale or failed;
- cap confidence when the top two phases are close;
- cap confidence during the first minimum-history window;
- cap confidence when query ambiguity or semantic collision is unresolved;
- never increase confidence solely because the model output is decisive on sparse inputs.

Thresholds must be configuration in a versioned methodology module, not scattered constants.

### 6.3 Machine-readable reasons

Each snapshot should store a confidence breakdown and reason codes:

```json
{
  "confidence": {
    "score": 47,
    "band": "low",
    "components": {
      "collection_completeness": 72,
      "source_breadth": 40,
      "freshness": 85,
      "independence": 35,
      "phase_separation": 31
    },
    "reasons": [
      {
        "code": "ADOPTION_EVIDENCE_WEAK",
        "severity": "high",
        "message": "Adoption is inferred mainly from repository activity; no independent implementation source was found.",
        "remediation": "Add package telemetry, public implementation reports, or a recurring adoption dataset."
      },
      {
        "code": "PHASE_SCORES_CLOSE",
        "severity": "medium",
        "message": "Innovation Trigger and Peak of Inflated Expectations are separated by only 4 points."
      }
    ]
  }
}
```

Initial reason-code catalog:

- `SOURCE_FAILURE`
- `SOURCE_STALE`
- `SOURCE_BREADTH_LOW`
- `FIRST_PARTY_DOMINANT`
- `INDEPENDENCE_LOW`
- `EVIDENCE_VOLUME_LOW`
- `ADOPTION_EVIDENCE_WEAK`
- `MATURITY_EVIDENCE_WEAK`
- `NEGATIVE_EVIDENCE_UNOBSERVED`
- `HISTORY_TOO_SHORT`
- `QUERY_AMBIGUOUS`
- `CLAIMS_CONFLICT`
- `PHASE_SCORES_CLOSE`
- `PHASE_UNSTABLE`
- `BACKFILL_ONLY_HISTORY`

### 6.4 User experience

Public technology pages should show:

- confidence band and score;
- the two or three strongest reasons lowering confidence;
- a compact component breakdown;
- the date and freshness of the latest successful source checks;
- clear wording that confidence describes evidence sufficiency and model separation, not statistical correctness.

Admin should additionally show:

- all reason codes and component values;
- affected sources and failed runs;
- suggested remediation;
- a link to retry or validate the relevant source;
- confidence change from the prior snapshot and what caused it.

### 6.5 Calibration

Confidence should be evaluated rather than tuned only by intuition.

Create a benchmark set containing technologies and weeks with:

- expert-reviewed evidence relevance;
- expert phase distributions rather than a forced single label;
- known source outages and sparse-data cases;
- ambiguous names and alias collisions;
- repeated press-release syndication;
- fizzled, superseded, and successfully maturing categories.

Track:

- agreement with reviewer phase distributions;
- confidence versus reviewer agreement;
- week-to-week stability under unchanged evidence;
- sensitivity to removing one source class;
- rate of high-confidence estimates later reversed without material new evidence;
- false confidence caused by duplicated or first-party evidence.

The score remains a diagnostic unless validation demonstrates probability calibration.

## 7. Fizzle-out and lifecycle exit

### 7.1 Vitality signal

Add a separate `vitality` assessment. It should not directly choose a lifecycle phase.

Inputs may include:

- release and commit recency;
- number and breadth of active maintainers;
- package download direction;
- repository archived/deprecated state;
- official deprecation or maintenance notices;
- developer discussion trend;
- independent implementation evidence;
- adoption and maturity trajectory;
- replacement or supersession evidence;
- ecosystem contraction across multiple source classes.

### 7.2 Avoid confusing quiet productivity with failure

A technology is not fizzled merely because attention declines. Plateau-stage technologies are expected to attract less hype.

An automated fizzle candidate should require all of the following categories of evidence:

1. **Weak durable use** — adoption remains below a calibrated threshold and has not grown over a sustained window.
2. **Weak operating maturity** — releases, maintenance, integrations, or operating practices remain sparse or contract.
3. **Negative trajectory** — momentum is persistently negative across more than one source class.
4. **Sufficient observation** — source coverage and historical depth are high enough to distinguish absence from collection failure.

Suggested initial review trigger, subject to benchmark calibration:

- at least 16 weekly snapshots;
- 12 consecutive weeks without meaningful adoption growth;
- adoption below 25 and maturity below 35;
- negative momentum in at least 8 of the last 12 weeks;
- no meaningful release or implementation evidence for 90 days;
- at least three applicable source classes checked successfully;
- no strong supersession, merger, or naming-ambiguity explanation left unresolved.

The trigger creates a review; it must not automatically remove a technology.

### 7.3 State machine

```text
active_weekly
├── sustained productivity ──> active_quarterly
├── weak vitality ───────────> exit_review
├── operator pause ──────────> paused
└── profile ambiguity ───────> needs_profile_review

exit_review
├── evidence recovers ───────> active_weekly
├── fizzled ─────────────────> exited:fizzled_out
├── replaced ────────────────> exited:superseded
├── merged ──────────────────> exited:merged_into_parent_category
└── insufficient identity ───> exited:insufficient_distinct_signal

exited
├── quarterly recheck finds recovery ──> reactivation_review
└── remains inactive ──────────────────> exited
```

### 7.4 Data model

Keep publication, cadence, and tracking outcome separate.

Proposed technology fields:

```text
publication_status: draft | validated | public | unlisted | archived
tracking_state: weekly | quarterly | exit_review | exited | paused
tracking_outcome: null | fizzled_out | superseded | merged_into_parent_category | insufficient_distinct_signal | operator_ended
outcome_reason: text
outcome_evidence_ids: list
outcome_decided_at: timestamp
outcome_decided_by: actor
next_reactivation_check_at: timestamp
```

Migration should map today's `active`, `paused`, and `archived` values without losing history.

### 7.5 Public behavior

When an operator confirms an exit:

- remove the technology from weekly analysis and the active homepage portfolio;
- preserve all snapshots, evidence, runs, and audit history;
- keep a stable, crawlable detail page unless legal or data-quality reasons require unlisting;
- show “Tracking ended” with the outcome, decision date, and supporting evidence;
- do not place an exited technology at a fabricated point on the curve;
- include an archived-technology filter or archive page once there are enough outcomes to justify it.

An exited technology should receive a cheap quarterly discovery check for renewed activity. Reactivation requires operator approval and resumes weekly analysis with a visible continuity note.

### 7.6 Admin workflow

Add an `Exit review` queue containing:

- vitality trend and triggering rules;
- last release, last independent adoption evidence, and last successful source checks;
- source-coverage sufficiency;
- candidate outcome and rationale;
- supporting and contradicting evidence;
- actions: keep weekly, move quarterly, pause, confirm outcome, merge profile, or request more evidence.

Every decision must write an audit event. Automatic suggestions cannot directly unpublish or exit a technology.

## 8. API and storage work

### 8.1 Storage migrations

Add versioned, additive migrations for:

- adapter/source configuration;
- per-source collection attempts;
- normalized evidence provenance and independence groups;
- quarantined records;
- confidence components and reason codes;
- vitality snapshots;
- technology tracking state and outcome decisions.

Retain snapshot payload compatibility during migration. Older snapshots should expose `confidence.reasons = [BACKFILL_ONLY_HISTORY]` or an equivalent legacy marker rather than pretending the new fields existed historically.

### 8.2 API additions

Proposed public fields/endpoints:

- confidence breakdown embedded in current and historical snapshots;
- `GET /api/v1/technologies/{id}/source-health`;
- tracking outcome on the public technology resource;
- active versus archived technology filters.

Proposed admin endpoints:

- source validate, retry, backfill, and replay;
- quarantined-record inspection;
- confidence-detail inspection;
- exit-review queue;
- tracking outcome decision and reactivation decision.

All state-changing endpoints require the existing admin authentication and audit actor.

## 9. Delivery sequence

### Phase 0 — methodology contract and fixtures

- Define source classes, claim types, independence groups, freshness policies, confidence components, and reason codes.
- Add representative benchmark fixtures before changing scores.
- Version the methodology and document backward compatibility.

Exit criteria:

- the new contracts are reviewed;
- old snapshots remain readable;
- benchmark cases cover sparse, conflicting, duplicated, stale, and fizzled evidence.

### Phase 1 — collector foundation

- Introduce the adapter interface and normalized envelope.
- Add source-run metrics, retries, cursors, quarantine, and replay.
- Refactor existing GitHub, Hacker News, and Google News collectors behind the interface without changing public scores.

Exit criteria:

- current output remains reproducible;
- partial failures do not replace last-known-good snapshots;
- one-source replay is idempotent;
- admin exposes actionable source errors.

### Phase 2 — first source expansion

- Add GitHub releases/security advisories, official feeds, direct publisher identity, package registries, and OSV.
- Add profile-driven applicability and admin validation.
- Backfill only sources whose APIs and policies support it.

Exit criteria:

- at least four independent source classes are available for representative technologies;
- attribution and first-party status are visible;
- source-specific freshness is measured.

### Phase 3 — confidence explanations

- Implement component scores, caps, reason codes, and remediation text.
- Show concise reasons publicly and complete diagnostics in admin.
- Add phase-perturbation tests for instability.

Exit criteria:

- every low/moderate confidence snapshot has at least one specific reason;
- high confidence cannot pass minimum evidence gates;
- reasons remain stable and reproducible for identical inputs.

### Phase 4 — independent adoption sources

- Add Stack Exchange, research metadata, and curated implementation reports.
- Introduce deterministic corroboration and independence grouping.
- Recalibrate adoption/maturity weights using benchmarks.

Exit criteria:

- repository activity is no longer the main adoption signal where better evidence exists;
- duplicated announcements do not materially inflate confidence;
- source-removal sensitivity tests pass.

### Phase 5 — vitality and exit review

- Compute vitality separately from lifecycle phase.
- Add the review trigger, admin queue, outcome states, and public archive behavior.
- Add quarterly reactivation checks.

Exit criteria:

- no automated rule can directly exit a technology;
- a confirmed exit preserves all history;
- quiet high-adoption technologies are not flagged as fizzled;
- fizzled benchmark cases enter review without being forced through later phases.

### Phase 6 — calibration and controlled rollout

- Run old and new confidence models in shadow mode for at least four weekly cycles.
- Compare phase changes, confidence changes, source reliability, and operator workload.
- Publish methodology-version notes before switching the public model.

Exit criteria:

- no unexplained phase or confidence changes;
- operational error budgets are met;
- rollback to the previous methodology version is tested.

## 10. Testing strategy

### Unit tests

- adapter normalization and validation;
- deterministic weight calculation;
- source freshness and independence grouping;
- confidence components, caps, and reason codes;
- vitality rules and quiet-productivity safeguards;
- state-transition validation.

### Integration tests

- partial source failure retains last-known-good public data;
- replay does not duplicate evidence;
- rate limits and malformed responses are visible and recoverable;
- admin decisions are authenticated and audited;
- exited technologies leave the active portfolio but retain detail/history access;
- reactivation restores cadence without losing earlier snapshots.

### Regression fixtures

- one announcement syndicated across many outlets;
- popular repository with no independent adoption evidence;
- mature technology with low news attention;
- ambiguous short technology name;
- rapidly growing technology with short history;
- technology that spikes, stalls, and is abandoned;
- technology superseded by a successor;
- source outage during an otherwise stable week.

## 11. Observability and reporting

Add metrics and structured events for:

- run success by adapter and technology;
- records received, accepted, deduplicated, and quarantined;
- source latency, freshness, and consecutive failures;
- evidence distribution by source class, claim type, and independence group;
- confidence band and reason-code distribution;
- confidence changes caused by source failures;
- technologies in exit review and time awaiting decision;
- false-positive exit reviews and reactivations.

Admin weekly summary should answer:

1. Which scheduled analyses did not publish and why?
2. Which technologies have low confidence and what evidence is missing?
3. Which source adapters are stale, failing, or producing unusually noisy data?
4. Which technologies entered exit review?
5. Which methodology or adapter version changed the result?

## 12. Credentials and external services

Recommended initial configuration:

- `GITHUB_TOKEN`: strongly recommended for rate-limit reliability;
- official feeds, npm, crates.io, Maven Central, and OSV: generally no key required;
- Stack Exchange: optional application key for higher quota;
- OpenAlex: identify requests according to its current usage policy;
- Reddit: OAuth credentials required if this adapter is approved;
- job, commercial-news, and procurement feeds: defer until a licensed provider is selected.

Credentials must remain environment variables or secret-store values. They must never be persisted in source configuration, evidence payloads, logs, or admin responses.

## 13. Definition of done

This plan is complete when:

- representative technologies use at least four relevant source classes;
- every estimate exposes source freshness and confidence reasons;
- a low-confidence estimate explains what is missing in plain language;
- high confidence requires independent adoption or maturity evidence;
- partial collection failures are replayable and cannot break public pages;
- repeated announcements cannot masquerade as independent corroboration;
- ARGUS can place a technology into an operator-reviewed exit state without forcing it through the whole lifecycle;
- exited technologies stop weekly checks while retaining an auditable public history;
- all model, source, confidence, and exit changes are versioned and reversible.
