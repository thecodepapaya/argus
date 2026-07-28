# Source, confidence, and lifecycle resilience plan

- Status: proposed, revised after implementation audit on 2026-07-28
- Scope: data collection, evidence quality, confidence explanations, and retirement of technologies that fizzle out
- Related documents: [implemented methodology](METHODOLOGY.md), [operations runbook](runbooks/OPERATIONS.md), [technology discovery](DISCOVERY.md)

This is an implementation plan, not a description of current behavior. Any item not also described in the implemented methodology must be treated as unshipped. Changes to collection, normalization, inference, confidence, or lifecycle state require a methodology-version change and migration notes.

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

### 2.1 Code-grounded gap inventory

The following risks exist in the current implementation and should be resolved before adding many more sources. They are ordered by their ability to create a confident but wrong public result.

| Priority | Current behavior | Risk | Required correction |
| --- | --- | --- | --- |
| P0 | Historical features are normalized against the maximum value across the entire reconstructed 52-week window | A historical week can use information from later weeks, creating look-ahead bias; reruns can rewrite old scores when a new maximum appears | Use as-of-week trailing baselines, record the normalization policy, and never use observations published after the target week |
| P0 | The current partial week is treated as a complete week; missing GitHub weekly aggregates become zero commits | Momentum can clamp to `-50` for active technologies merely because GitHub's aggregate has not settled | Mark periods `open`, `settling`, or `closed`; compare only equivalent elapsed portions or publish momentum as unavailable until the period closes |
| P0 | `coverage` is inferred partly from commits, discussion counts, repository count, and evidence volume | The displayed percentage does not reliably answer whether applicable collectors succeeded | Compute collection completeness from an explicit applicability matrix and attempt outcomes; keep evidence volume separate |
| P0 | A collection writes snapshots/evidence and commits before the run record is created | A failure between those steps can expose new public data without a matching run manifest or audit trail | Stage a run, validate it, and atomically promote its immutable output and completion record in one transaction |
| P0 | Partial source runs still replace current estimates without minimum evidence gates | A dependency outage can cause a phase change that looks analytical rather than operational | Abstain and retain the last-known-good public snapshot when required gates fail; show the attempted run separately |
| P1 | Source weights and keyword rules are hardcoded in `live.py` | Policy changes are difficult to reproduce, review, or compare | Move them to a versioned methodology policy with reasoned claim-specific weights |
| P1 | GitHub evidence is always marked independent and Google News is stored as one publisher | Official repositories can be misclassified as independent, while syndicated publisher identity is lost | Resolve publisher, ownership, first-party relationship, canonical URL, and event cluster before weighting |
| P1 | Source status has one row per broad source class, and a failed attempt can overwrite the prior success timestamp | Per-repository failures, empty responses, stale success, and last-known-good state cannot be distinguished | Store append-only collection attempts per configured source instance; derive current health without erasing history |
| P1 | Every refresh reconstructs and upserts 52 weeks, with no revision ledger | Historical estimates can change silently and comparisons may mix methodology versions | Make observations and derived snapshots immutable by run/methodology version; publish explicit superseding revisions |
| P1 | Evidence that disappears from a later collection has no validity interval or superseded state | Old records can remain indistinguishable from current evidence | Add `valid_from`, `valid_to`, `last_observed_at`, and `superseded_reason`; define which evidence contributes to each snapshot |
| P1 | Headline substring matching determines relevance and claim dimension | Ambiguous names, negation, quoted claims, and keyword precedence can misclassify evidence | Add deterministic identity gates, ambiguity flags, review sampling, and an abstaining `unclassified` outcome |
| P2 | “Verified adoption” is still derived largely from bounded repository activity | The label overstates what the input proves | Rename the internal component to `adoption_signal` until named implementation evidence exists; expose provenance by claim strength |

### 2.2 Immediate safety invariants

These invariants apply before any scoring improvement:

1. A failed or incomplete run cannot replace the last-known-good public snapshot unless its publication gate explicitly passes.
2. A historical snapshot uses only evidence available on or before its `as_of` time.
3. A zero measurement is never substituted for an unavailable, not-yet-settled, or failed measurement.
4. The same immutable input manifest, methodology version, and code version reproduce the same derived snapshot.
5. Every public snapshot points to exactly one completed run manifest and a complete set of contributing evidence IDs.
6. Review decisions survive recollection; evidence content revisions are separately versioned.
7. No evidence item contributes more than once to a claim cluster, regardless of syndication count.
8. Missing negative evidence is represented as missing, not as proof that no disappointment exists.
9. A technology profile cannot be published until its identity, aliases, exclusions, and source applicability are validated.
10. ARGUS may abstain. “Insufficient evidence” is a valid weekly result and must not be coerced into a lifecycle phase change.

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

### 3.4 Observations, features, estimates, and publication are separate layers

ARGUS needs four immutable boundaries:

```text
raw observation -> normalized evidence -> derived feature set -> lifecycle estimate -> public publication pointer
```

- Raw observations preserve what an adapter returned, within retention and licensing limits.
- Normalized evidence records identity, claim, provenance, and quality policy without embedding a phase.
- Feature sets are reproducible derivations for one `technology_id × as_of × methodology_version`.
- Estimates consume only a feature set and prior eligible state.
- Publication atomically moves a pointer to a validated estimate; it never mutates the previous public result.

This separation enables replay, audit, corrections, and shadow models without recollecting the internet or silently changing history.

### 3.5 Missingness is data

Every input must distinguish:

- `observed_zero` — the source successfully reported no qualifying activity;
- `not_applicable` — the source is irrelevant to this technology;
- `not_collected` — the adapter was not scheduled or configured;
- `collection_failed` — an attempt failed;
- `settling` — the measurement window is incomplete or the upstream aggregate is delayed;
- `stale` — a prior value exists but is older than policy allows;
- `suppressed` — a record was quarantined, excluded, or cannot be retained.

Feature code must not coerce these states to zero. Confidence and publication gates consume missingness explicitly; phase scoring receives a value only when the feature policy says it is usable.

### 3.6 Abstention and correction are first-class outcomes

For each scheduled analysis, ARGUS may produce:

- `published` — a new estimate passed all gates;
- `unchanged` — new evidence was checked but did not justify a new estimate;
- `partial_observation` — useful inputs arrived, but publication gates failed;
- `insufficient_evidence` — ARGUS cannot support a current estimate;
- `invalidated` — a previously published estimate was withdrawn because of a data or methodology defect;
- `corrected` — a new immutable revision supersedes a prior estimate.

Public pages should continue serving the last valid estimate with an “as of” date and freshness warning. Corrections require a reason, actor, affected versions, and an audit event; old URLs and API consumers must be able to identify the superseding revision.

### 3.7 Keep confidence independent from lifecycle shape

Confidence must assess whether inputs and inference are trustworthy, not whether a result looks like a familiar hype-cycle trajectory. Continuity and hysteresis may stabilize phase selection, but they cannot increase evidence quality. A decisive score produced by one narrow proxy remains low confidence. Confidence components must therefore be computed outside phase scoring and must not reward conformity to an expected sequence.

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

### 4.5 Technology identity and query governance

Source expansion will amplify ambiguity unless ARGUS first defines what each tracked entity means. Every profile should include:

```json
{
  "identity": {
    "canonical_name": "Model Context Protocol",
    "aliases": ["MCP"],
    "required_context_terms": ["AI", "model context"],
    "excluded_meanings": ["Microsoft Certified Professional"],
    "parent_category": "agent interoperability protocols",
    "successor_ids": [],
    "geographies": ["global"],
    "languages": ["en"]
  },
  "query_policy_version": "identity-v1"
}
```

- Short or overloaded aliases require contextual terms; an alias alone is not a match.
- Queries, relevance terms, exclusions, and source applicability are versioned together.
- A query change creates a comparability boundary. Backfill with the new query is stored as a new revision rather than blended silently with the old series.
- Parent/child profiles must declare overlap rules so one event is not counted as independent evidence for both a framework and its broader category without disclosure.
- Merge, split, and rename operations preserve stable IDs and create redirects/relationships instead of rewriting old evidence ownership.
- Profile validation should run a sample query and show estimated precision, collisions, excluded results, and empty-source warnings before publication.

### 4.6 Bias, language coverage, and manipulation resistance

ARGUS is vulnerable to coordinated announcements, repository gaming, bot discussions, SEO spam, and English/open-source selection bias. The methodology should therefore:

- cap the influence of any publisher, repository, community, vendor, or claim cluster;
- detect sudden low-quality source concentration and abnormal star/download/comment bursts;
- record suspected automation, promotional language, affiliate content, and undisclosed first-party relationships as quality flags;
- exclude visitor suggestions and LLM discovery output from lifecycle evidence until a normal adapter independently collects it;
- publish language and geography coverage for each technology;
- avoid comparing absolute activity between ecosystems with materially different source availability;
- maintain adversarial fixtures for press-release floods, link farms, repository-star spikes, and duplicated vendor case studies;
- require human review before a manipulation flag suppresses otherwise attributable evidence.

These controls reduce influence; they do not assert fraud or remove source records from the audit ledger.

### 4.7 Source admission and retirement policy

Adding an adapter is a methodology change, not merely an integration task. Before activation, document:

- terms of service, robots/API policy, permitted retention, attribution, and redistribution;
- expected availability, latency, quota, and backfill behavior;
- target technologies and claim types;
- precision/recall on a reviewed sample;
- overlap with existing sources and likely independence group;
- cost ceiling and behavior when credentials or budget are exhausted;
- an owner, operational runbook, and removal plan.

Run new sources in shadow mode first. A source can be disabled without making old snapshots unreadable; its historical observations retain adapter and policy versions. Remove or downgrade sources that remain noisy, legally uncertain, operationally unreliable, or redundant after a documented review.

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

Define the measurement window for each objective and publish both the target and actual value in admin. “Completed” means a terminal run outcome with a manifest; a process that disappeared without recording failure does not count as completed.

### 5.5 Run manifest and atomic publication

Every collection/analysis attempt should begin with a durable run record and end in one transaction. The manifest should contain:

```text
run_id / technology_id / scheduled_for / as_of
code_revision / methodology_version / profile_version
adapter_versions / query_policy_version
source_attempt_ids / input_observation_ids
normalization_window / feature_set_id / estimate_id
gate_results / terminal_status / error_codes
started_at / completed_at / published_at
```

Recommended state flow:

```text
scheduled -> collecting -> normalizing -> scoring -> validating
          -> publishable -> published
          -> partial_observation | insufficient_evidence | failed | cancelled
```

- Staged observations may be committed incrementally, but the public publication pointer and terminal run record move atomically.
- A lease/heartbeat identifies abandoned runs after process death; takeover uses the same idempotency key.
- Only one publish lease exists for `technology_id × scheduled_for × methodology_version`.
- Retrying a terminal run creates a linked attempt, not a second indistinguishable run.
- Public reads never assemble a snapshot from partially written tables.

### 5.6 Time semantics, settling windows, and backfills

Store at least four times: `event_at`, `published_at`, `first_observed_at`, and `collected_at`. The feature policy declares which time it uses.

- Weekly windows use UTC boundaries and a documented timezone-independent `as_of` instant.
- Sources with delayed aggregates have a source-specific settling period. An open week may show provisional source health but cannot masquerade as a closed-period momentum value.
- Backfills run in strict as-of mode: evidence published later cannot influence an earlier historical estimate, even if it describes an earlier event.
- Corrections to publication dates or source content produce a new observation revision.
- Late-arriving evidence may create a historical correction, but never silently changes an already published snapshot.
- Comparisons use like-for-like window completeness. A three-day partial week is not compared with seven complete days without explicit partial-window normalization.

### 5.7 Data-quality gates

Before scoring, validate:

- schema and permitted value ranges;
- temporal consistency and future dates;
- canonical identity and technology relevance;
- duplicate/event-cluster membership;
- source applicability, success, freshness, and retention permission;
- minimum claim/dimension coverage;
- distribution shifts against the adapter's recent baseline;
- impossible jumps or flatlined fallback values;
- provenance completeness and reproducible weights.

Gate outcomes are machine-readable. Quarantine never means deletion: store a safe diagnostic record with the reason and payload hash, while respecting content-retention policy. An operator can approve, correct, or permanently exclude a quarantined record with an audit event.

### 5.8 Backup, restore, and disaster recovery

SQLite durability is not a backup strategy. Define:

- encrypted daily backups of the database plus WAL-consistent snapshot procedure;
- retention tiers (for example 7 daily, 8 weekly, and 12 monthly copies) appropriate to cost;
- an off-host copy and periodic integrity checks;
- documented recovery point and recovery time objectives; initial targets: RPO 24 hours, RTO 4 hours;
- quarterly restore drills into an isolated environment;
- export/import of methodology policies, technology profiles, and publication pointers;
- verification that secrets, raw restricted content, and transient caches are excluded;
- rollback procedure for both application image and schema migration.

The committed showcase fixture is a bootstrap convenience, not the recovery source for operational reviews, run history, suggestions, or audit records.

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
- `CURRENT_PERIOD_SETTLING`
- `NORMALIZATION_BASELINE_WEAK`
- `SOURCE_CONCENTRATION_HIGH`
- `PUBLICATION_GATE_FAILED`
- `METHODOLOGY_MIXED_HISTORY`

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

### 6.6 Feature and confidence scoring contract

Before implementation, write a machine-readable policy for every feature and confidence component:

| Required field | Example question |
| --- | --- |
| Input claim types | Which normalized claims may contribute? |
| Applicability | Which source classes are expected for this technology? |
| Aggregation unit | Is the unit a claim cluster, organization, repository, publisher, or week? |
| Transform | How are heavy tails, scale, and outliers handled? |
| Baseline | Is normalization trailing, cohort-relative, or absolute? |
| Missingness | Which missing states cause abstention, imputation, or a confidence penalty? |
| Caps | What prevents one source or event from dominating? |
| Freshness | When does the input decay or expire? |
| Version | Which policy and code revision produced the value? |

First implementation principles:

- Use robust trailing baselines (median/MAD, percentile rank, or documented bounded transforms) rather than a maximum across the full backfill window.
- Require a minimum number of closed periods before publishing directional momentum.
- Compute per-source momentum first, then combine only comparable, available source classes; expose disagreement.
- Keep absolute level and direction separate. A mature, stable ecosystem can have high adoption with near-zero momentum.
- Avoid cross-technology rankings until source applicability and scale normalization make comparisons defensible.
- Store unrounded internal values, but round only at presentation boundaries.
- Produce a contribution trace showing each usable input, transform, cap, and resulting component value.

Do not assign final numeric weights until the benchmark set and ablation tests exist. The plan's component list is a design constraint, not a pre-approved formula.

### 6.7 Phase stability and transition safeguards

Continuity should prevent noise, not force the Gartner-shaped path. Add:

- a minimum evidence-change threshold before a phase transition;
- hysteresis bands so a technology does not oscillate at a boundary;
- explicit support for a backwards move when evidence materially changes;
- no automatic multi-stage jump unless the evidence delta and phase separation exceed a stronger gate;
- perturbation analysis that recomputes the estimate after removing each source class and after bounded input changes;
- `PHASE_UNSTABLE` when plausible perturbations change the winning phase;
- a public “unchanged due to insufficient new evidence” outcome instead of relying only on continuity bonus;
- transition reason codes listing the changed features and evidence clusters.

The previous phase may influence selection, but it must never affect the confidence component for evidence quality. State-transition rules and their thresholds belong to the methodology version.

### 6.8 Evaluation protocol and release threshold

Split benchmark data into development and locked evaluation sets. Include technologies from different lifecycle stages, ecosystem sizes, licensing models, and source availability profiles. For each reviewed item:

- use at least two reviewers and adjudicate material disagreements;
- record reviewer confidence and acceptable phase distribution;
- measure inter-rater agreement rather than treating one label as ground truth;
- freeze evidence at an as-of timestamp to prevent leakage;
- record whether the case is native historical data, backcast data, or synthetic failure injection;
- prevent examples used to tune thresholds from serving as release evidence.

Minimum release report:

1. relevance precision by source and technology profile;
2. claim-type precision and abstention rate;
3. phase-distribution agreement and transition stability;
4. confidence reliability by band;
5. sensitivity to source removal, stale inputs, and duplicate floods;
6. error rates for ambiguous identities and quiet mature technologies;
7. operator review volume and median time to resolve;
8. results sliced by source class, language, and technology type.

A new methodology must beat or explain regressions against the current version on the locked set. Raw aggregate improvement cannot hide a severe regression in adoption evidence, identity precision, or false-high-confidence rate.

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

### 7.7 Exit-review safeguards

- A source outage, query change, profile rename, or settling period suspends vitality decisions for the affected window.
- Exit rules operate on closed periods and source-specific missingness, not the current partial week.
- At least one reviewer must inspect counter-evidence and possible successor/parent relationships before confirmation.
- Fizzle and supersession decisions require different evidence; replacement mentions must not be treated as abandonment automatically.
- A merged profile records evidence-allocation rules and redirects, preventing double counting after the merge.
- Exit recommendations expire if not reviewed within a configured period and must be recomputed from fresh data.
- Track false-positive exit reviews, operator reversals, and time-to-reactivation as model-quality metrics.
- Reactivation creates a new tracking episode linked to the old one; it does not erase the prior outcome or pretend monitoring was continuous.

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

### 8.3 Storage ownership and API contracts

Prefer normalized tables for queryable identity, provenance, attempts, reviews, and publication state; JSON payloads remain useful for immutable versioned manifests but should not be the only source of operational truth.

Minimum entities:

```text
technology_profile_versions     source_config_versions
collection_runs                 collection_attempts
raw_observations                evidence_revisions
claim_clusters                  evidence_cluster_members
feature_sets                    estimates
confidence_reasons              publications
review_decisions                vitality_assessments
tracking_outcomes               audit_events
```

Contract requirements:

- stable opaque IDs and explicit schema/methodology versions;
- cursor pagination and bounded filters for evidence, attempts, and revisions;
- conditional writes or idempotency keys for retries;
- explicit `as_of`, `generated_at`, `published_at`, and freshness fields;
- an `is_provisional`/terminal-status distinction;
- links from public values to contributing evidence and run manifest;
- safe error codes that do not expose credentials or restricted content;
- backward-compatible additive API changes within a version, with deprecation notice before removal;
- database constraints for legal state transitions, uniqueness, foreign keys, and one active publication pointer per technology;
- migrations that are transactional where SQLite permits and resumable otherwise.

Large evidence exports and raw diagnostics remain admin-only. Public APIs expose permitted excerpts, attribution, derived values, and provenance—not secrets, full copyrighted bodies, quarantine payloads, or private review notes.

## 9. Delivery sequence

### Phase 0 — methodology contract and fixtures

- Define source classes, claim types, independence groups, freshness policies, confidence components, and reason codes.
- Add representative benchmark fixtures before changing scores.
- Version the methodology and document backward compatibility.

Exit criteria:

- the new contracts are reviewed;
- old snapshots remain readable;
- benchmark cases cover sparse, conflicting, duplicated, stale, and fizzled evidence.

### Phase 0A — current-model safety repairs

Complete this before onboarding new source adapters:

- stop treating the open current week and delayed GitHub aggregates as observed zero;
- replace full-window maximum normalization with closed-period trailing baselines;
- separate collector completion from evidence volume in coverage;
- add publication gates and an explicit `insufficient_evidence` outcome;
- preserve last-known-good source success timestamps and public snapshots;
- create the run record before collection and atomically finalize publication;
- add `as_of`, period status, input manifest, and methodology version to derived snapshots;
- relabel or clearly qualify repository-derived adoption until independent evidence exists.

Exit criteria:

- an active repository with an unsettled current aggregate does not receive artificial `-50` momentum;
- recomputing a historical week cannot see later evidence or later normalization maxima;
- injected failure at every publication step leaves either the old public snapshot or one complete new snapshot, never a mixed state;
- zero, failed, stale, settling, and not-applicable inputs remain distinguishable through the API and admin UI;
- a partial run cannot change the public phase unless its configured publication gates pass.

### Phase 1 — collector foundation

- Introduce the adapter interface and normalized envelope.
- Add source-run metrics, retries, cursors, quarantine, and replay.
- Refactor existing GitHub, Hacker News, and Google News collectors behind the interface, preserving Phase 0A semantics and recording any unavoidable score change as a methodology revision.

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

- at least four relevant source classes and at least two genuinely independent source groups are available for representative technologies;
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
- state-transition validation;
- missingness propagation without zero coercion;
- trailing-baseline calculations with no future observations;
- property tests for bounds, monotonic caps, idempotency keys, and legal transitions;
- query identity rules for aliases, exclusions, Unicode, punctuation, and case folding.

### Integration tests

- partial source failure retains last-known-good public data;
- replay does not duplicate evidence;
- rate limits and malformed responses are visible and recoverable;
- admin decisions are authenticated and audited;
- exited technologies leave the active portfolio but retain detail/history access;
- reactivation restores cadence without losing earlier snapshots;
- failure injection between each storage/publication step proves atomic visibility;
- concurrent scheduler/retry attempts cannot publish two results for the same run key;
- evidence review decisions survive recollection and evidence revision;
- mixed methodology versions remain explicit in history and comparisons;
- backup restore recreates publication pointers, audit history, and source attempts.

### Adapter contract tests

Each adapter ships recorded, license-safe fixtures for success, empty success, pagination, rate limiting, authentication failure, timeout, malformed payload, schema drift, duplicate pages, delayed data, and cursor resume. Live canary tests run separately so upstream instability cannot make the deterministic test suite flaky.

### Time-travel and backfill tests

- Freeze the clock at each historical week and assert that later observations are inaccessible.
- Re-run the same as-of manifest after newer data arrives and require byte-equivalent features/estimates.
- Verify partial-week comparisons use equal elapsed windows or abstain.
- Verify late-arriving evidence creates an explicit correction rather than mutating the original publication.
- Verify query/profile revisions do not silently blend incompatible histories.

### Resilience and security tests

- dependency latency, timeouts, HTTP error bursts, invalid certificates, and quota exhaustion;
- process termination during collection, validation, publication, and migration;
- disk-full, read-only database, WAL recovery, and corrupted-backup drills in disposable environments;
- untrusted HTML, prompt-injection text, oversized fields, malicious URLs, SSRF attempts, and log/control-character injection;
- authorization and CSRF expectations for every admin mutation;
- secret redaction from logs, errors, manifests, exports, and evidence payloads.

### Regression fixtures

- one announcement syndicated across many outlets;
- popular repository with no independent adoption evidence;
- mature technology with low news attention;
- ambiguous short technology name;
- rapidly growing technology with short history;
- technology that spikes, stalls, and is abandoned;
- technology superseded by a successor;
- source outage during an otherwise stable week;
- current week with delayed GitHub aggregate but recent repository activity;
- historical spike that would distort full-window maximum normalization;
- zero activity returned successfully versus a failed/settling source;
- first-party announcement repeated by nominally different publications;
- coordinated star/download/comment spike;
- query-policy change that alters historical recall;
- one phase boundary under small input perturbations;
- a corrected publication with preserved prior revision.

## 11. Observability and reporting

Add metrics and structured events for:

- run success by adapter and technology;
- records received, accepted, deduplicated, and quarantined;
- source latency, freshness, and consecutive failures;
- evidence distribution by source class, claim type, and independence group;
- confidence band and reason-code distribution;
- confidence changes caused by source failures;
- technologies in exit review and time awaiting decision;
- false-positive exit reviews and reactivations;
- publication age, last-known-good age, abstention rate, and correction rate;
- lock/lease contention, abandoned runs, retry amplification, and queue delay;
- backup age, backup verification, and restore-drill outcome.

Every event should carry `run_id`, `technology_id`, `source_config_id`, `adapter_version`, `profile_version`, `methodology_version`, and request/trace ID where applicable. Metrics must use bounded-cardinality labels; evidence IDs and URLs belong in logs/traces, not metric labels.

Initial alerts:

- a scheduled run has no terminal outcome by its deadline;
- a public estimate exceeds its freshness policy;
- any required source is stale beyond one analysis window;
- consecutive failures open a circuit or affect more than a configured share of technologies;
- accepted/received ratio, duplicate ratio, or quarantine ratio shifts materially from baseline;
- a phase changes during a partial run, methodology mix, or failed publication gate;
- high confidence is emitted without all high-confidence gates;
- backup age exceeds RPO or a restore verification fails.

Alerts should link to the run, affected technologies, reason code, last success, retry state, and runbook. Avoid paging for a single optional-source failure when public data remains fresh; alert severity follows user impact and time-to-staleness.

Admin weekly summary should answer:

1. Which scheduled analyses did not publish and why?
2. Which technologies have low confidence and what evidence is missing?
3. Which source adapters are stale, failing, or producing unusually noisy data?
4. Which technologies entered exit review?
5. Which methodology or adapter version changed the result?

## 12. Data governance, security, and cost controls

### 12.1 Retention and licensing

- Maintain a per-source data inventory covering fields retained, lawful/contractual basis, attribution, redistribution, retention, and deletion procedure.
- Prefer IDs, URLs, titles, hashes, and short permitted excerpts; do not retain full article bodies by default.
- Apply source-specific retention automatically and record tombstones/hashes needed for audit without retaining prohibited content.
- Provide a correction/removal workflow for broken attribution, publisher requests, personal data, and legally restricted material.
- Preserve derived aggregate reproducibility where possible, but invalidate and republish when source deletion makes a material claim unsupported.
- Document whether archived public pages remain indexable after tracking ends.

### 12.2 Security boundaries

- Treat feeds, titles, excerpts, URLs, repository metadata, visitor suggestions, and LLM output as untrusted input.
- Use an outbound-host allowlist or adapter-owned URL templates; profile-supplied URLs must pass scheme, DNS/IP, redirect, and private-network checks to prevent SSRF.
- Escape output by context and sanitize permitted markup; never render source HTML directly.
- Enforce response-size, decompression, redirect, pagination, and processing-time limits.
- Keep LLM discovery/enrichment isolated from deterministic evidence scoring. Retrieved text cannot change tools, credentials, system prompts, publication state, or methodology.
- Require strong admin authentication in production, rate-limit login and mutation endpoints, document CSRF policy, and rotate/audit credentials.
- Sign or checksum exported manifests and backups; restrict raw observation and quarantine access by role.
- Run dependency, container, and secret scanning in CI; patch critical collector/network vulnerabilities under a defined SLA.

### 12.3 Cost and quota budgets

Each adapter and LLM workflow needs a weekly request/token budget, per-run ceiling, and graceful exhaustion behavior. Cache permitted responses, honor conditional requests, and prioritize active technologies and required sources. Cost exhaustion results in `not_collected:budget_exhausted`, never zero activity. Admin should show current usage, forecast, quota resets, and which analyses will be affected.

## 13. Credentials and external services

Recommended initial configuration:

- `GITHUB_TOKEN`: strongly recommended for rate-limit reliability;
- official feeds, npm, crates.io, Maven Central, and OSV: generally no key required;
- Stack Exchange: optional application key for higher quota;
- OpenAlex: identify requests according to its current usage policy;
- Reddit: OAuth credentials required if this adapter is approved;
- job, commercial-news, and procurement feeds: defer until a licensed provider is selected.

Credentials must remain environment variables or secret-store values. They must never be persisted in source configuration, evidence payloads, logs, or admin responses.

Production readiness should validate required credentials and model/source capabilities before the scheduler starts. A missing optional credential disables only its adapter with a visible reason. A missing required credential fails readiness without repeatedly launching doomed collection runs.

## 14. Decisions required before Phase 1

Resolve and record these as ADRs or methodology decisions:

1. What is the precise tracked entity: named product, implementation, protocol, or category, and when are parent/child profiles both allowed?
2. Which source classes are required versus optional for each technology type?
3. What closes a weekly period for each delayed source, and when may provisional values appear publicly?
4. What minimum publication gates permit a partial run to replace the last-known-good estimate?
5. Which observation fields may be retained for each proposed source and for how long?
6. Which independent evidence qualifies the public label “verified adoption,” or should that label change first?
7. What reviewer process and locked benchmark set authorize methodology changes?
8. What are acceptable false-high-confidence, false-exit-review, abstention, and correction rates?
9. What are production RPO/RTO, alert destinations, and on-call ownership?
10. Which API compatibility promise and historical-revision policy will public consumers receive?

Unresolved decisions must be explicit blockers, not hidden defaults chosen inside adapters.

## 15. Definition of done

This plan is complete when:

- representative technologies use at least four relevant source classes;
- every public snapshot is linked to an immutable completed run/input manifest and was promoted atomically;
- historical recomputation is as-of correct and has no future-data or full-window-normalization leakage;
- unavailable, failed, stale, settling, not-applicable, and observed-zero inputs remain distinct;
- every estimate exposes source freshness and confidence reasons;
- a low-confidence estimate explains what is missing in plain language;
- high confidence requires independent adoption or maturity evidence;
- publication may abstain; partial collection failures are replayable and cannot break or silently move public pages;
- repeated announcements cannot masquerade as independent corroboration;
- technology identity/query versions make ambiguous terms and history boundaries explicit;
- source-admission, retention, security, cost, and removal policies exist for every enabled adapter;
- the locked evaluation report meets agreed thresholds and includes slice/ablation results;
- ARGUS can place a technology into an operator-reviewed exit state without forcing it through the whole lifecycle;
- exited technologies stop weekly checks while retaining an auditable public history;
- backup restore and application/schema rollback have been exercised successfully;
- all model, source, confidence, correction, and exit changes are versioned, auditable, and reversible.
