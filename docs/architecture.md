## Architecture and developer guide

This document is for maintainers and future AI agents working on `moodle-sitemap`. It explains how the codebase is structured today, which invariants matter, and how to extend the project without breaking the saved artifact contract.

### Project shape

The codebase is intentionally file-based and JSON-first:

- no database
- no LLM dependency
- no workflow execution engine
- no hidden persistence beyond timestamped run folders

The main design idea is:

1. crawl with a real authenticated browser
2. derive stable page records
3. derive graph, summaries, comparisons, and task-validation results from those records

Everything downstream should be explainable from saved artifacts.

### Core responsibilities

#### Entry points

- [`src/moodle_sitemap/cli.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/cli.py)
  - exposes `smoke`, `crawl`, `verify`, `discover`, `compare-runs`, and `validate-tasks`
  - should stay thin and mostly delegate to library code

#### Browser and authentication

- [`src/moodle_sitemap/browser.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/browser.py)
  - launches Playwright browsers
- [`src/moodle_sitemap/auth.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/auth.py)
  - handles the Moodle login flow

#### Crawl and storage

- [`src/moodle_sitemap/crawl.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/crawl.py)
  - owns crawl orchestration
  - turns rendered pages into `PageRecord` values
  - runs classification, safety summarization, workflow derivation, and manifest writing
- [`src/moodle_sitemap/storage/json_store.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/storage/json_store.py)
  - writes page, manifest, and workflow JSON artifacts

#### Discovery and normalization

- [`src/moodle_sitemap/discover.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/discover.py)
  - URL normalization
  - canonicalization helpers
  - safe-link filtering
  - page-id generation

#### Extraction

- [`src/moodle_sitemap/extract/dom.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/extract/dom.py)
  - extracts body metadata, breadcrumbs, affordances, and task-summary hints
  - this is the largest extraction hotspot in the repo
- [`src/moodle_sitemap/extract/footer.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/extract/footer.py)
  - parses raw Moodle footer/performance text conservatively
- [`src/moodle_sitemap/extract/network.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/extract/network.py)
  - records and redacts page-load network events

#### Classification and safety

- [`src/moodle_sitemap/classify/page_type.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/classify/page_type.py)
  - route-aware Moodle page classification
  - should stay conservative and deterministic
- [`src/moodle_sitemap/safety.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/safety.py)
  - page-level risk summary from affordance hints

#### Graph and downstream analysis

- [`src/moodle_sitemap/workflow.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/workflow.py)
  - high-level workflow orchestration
- [`src/moodle_sitemap/workflow_support.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/workflow_support.py)
  - edge candidate collection
  - weighting, de-noising, compression, and `next_steps` ranking helpers
- [`src/moodle_sitemap/discovery.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/discovery.py)
  - builds post-run discovery summaries and markdown reports
- [`src/moodle_sitemap/compare_runs.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/compare_runs.py)
  - compares two saved runs
- [`src/moodle_sitemap/task_validation.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/task_validation.py)
  - high-level task-validation orchestration
- [`src/moodle_sitemap/task_validation_support.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/task_validation_support.py)
  - path finding, scoring, affordance selection, and report helpers

#### Shared models

- [`src/moodle_sitemap/models.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/models.py)
  - artifact contract
  - enums
  - shared Pydantic models for pages, summaries, comparisons, and task validation

### Artifact lifecycle

The artifact chain matters more than any single module:

1. `smoke` writes a single `smoke-test.json`
2. `crawl` writes:
   - `pages/*.json`
   - `sitemap.json`
   - `workflow-edges.json`
3. `verify` wraps `smoke` + small `crawl`
4. `discover` wraps broader `crawl` + `discovery-summary.json` + `discovery-summary.md`
5. `compare-runs` reads two saved runs and emits role comparison artifacts
6. `validate-tasks` reads one saved run and emits task-validation artifacts

Important consequence:

- downstream tools should not need hidden in-memory state to understand a run
- if a field is relied on for ranking or validation, prefer serializing it explicitly

### Important invariants

These are the invariants future changes should preserve unless there is a deliberate contract change:

- `normalized_url` is the conservative canonical URL used for de-duplication and stable reporting
- page identity is role-neutral; visibility changes by role, but `page_type` should still represent page identity, not privilege
- affordance, safety, and task-intent hints are heuristic and conservative, not claims of certainty
- workflow edges should prefer explicit high-signal paths over generic discovered-link noise
- low-value repeated navigation can be compressed, but strong task/support edges must remain explicit
- saved page artifacts should expose the derived fields that downstream logic depends on
- task validation inspects saved artifacts only; it does not drive the browser

### Testing strategy

The repo intentionally leans on fast deterministic tests instead of broad browser-heavy suites.

Use tests in three layers:

- unit tests
  - normalization, classification, extraction helpers, weighting, scoring, and schema behavior
- integration-style tests
  - manifest + workflow + comparison + task-validation behavior from synthetic saved artifacts
- regression tests
  - bugs that already happened once and must not reappear

Regression categories already protected include:

- canonical redirect duplication
- malformed form ID extraction
- false-positive dashboard classification for messaging pages
- lower-privilege route classification gaps
- graph de-noising and edge-compression behavior
- derived-field serialization mismatches

### How to extend the project safely

#### Add a new page type

1. add it to [`models.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/models.py)
2. add a conservative rule in [`classify/page_type.py`](/Users/mattp/projects/agentic_sitemap/src/moodle_sitemap/classify/page_type.py)
3. add route-based tests
4. rerun discovery/role comparison if the type affects real surfaced pages

Do not add a new type just because a page is visible to a certain role. Page types model page identity, not permissions.

#### Extend affordances

Prefer:

- deterministic extraction
- scalar normalized fields
- defensive handling of malformed markup

Avoid:

- leaking raw Playwright/DOM object shapes into models
- adding fields that downstream code silently depends on but artifacts do not serialize

#### Change workflow weighting

When adjusting edge weighting or `next_steps`:

- preserve explicit task/support edges
- be careful with discovered-link fallbacks
- prefer transparent rules and tests over opaque scoring
- add regression coverage for the route family or page type you touched

#### Change task validation

Task validation is intentionally practical, not a formal planner. Changes should keep result semantics easy to explain:

- `pass`: target found and path is clear enough
- `partial`: target exists but path or affordances are weak
- `fail`: target missing or path unusable

If you add new metadata, keep it inspectable and make sure it is reflected in the JSON artifact.

### Known weak spots

These areas are intentionally conservative or still somewhat noisy:

- `extract/dom.py` contains a lot of browser-side extraction logic and remains the densest module
- safety signals are useful but can over-warn on complex admin pages
- lower-signal social surfaces such as forum-user pages still have weaker affordance quality than course/admin/preferences surfaces
- some route families intentionally stay grouped into practical buckets rather than many narrow page types

### Recommended maintenance workflow

For non-trivial changes:

1. update docs if the contract or workflow changes
2. add or tighten tests for the intended invariant
3. refactor only after the test net is in place
4. rerun `pytest`
5. rerun the smallest relevant saved-run workflow only if the artifact contract changed

That order keeps behavior changes deliberate and makes the project easier for future humans and AI agents to trust.
