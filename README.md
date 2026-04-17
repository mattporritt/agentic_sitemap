# moodle-sitemap

`moodle-sitemap` is a phase 1 Moodle-aware authenticated sitemap builder for browser-assisted tooling. It logs into a Moodle LMS with supplied credentials, crawls a bounded set of same-origin pages using a real browser, and writes a structured JSON sitemap to disk.

This first version is intentionally narrow. The goal is to produce a dependable crawl artifact that future tooling can build on, not to solve every Moodle automation problem in one go.

## Why this exists

Moodle sites are heavily authenticated, dynamic, and often shaped by role-based navigation, AJAX flows, and LMS-specific page patterns. A requests-only crawler tends to miss too much. This project uses Playwright so the crawler behaves more like a real user session while still keeping the scope production-sensible.

This project is also intentionally AI agnostic. The core crawler does not depend on LLMs, agent frameworks, LangChain, MCP, or SQLite.

## What problem it solves

Moodle is difficult to map with lightweight crawlers because the useful surface area is mostly authenticated, role-sensitive, and rendered dynamically in the browser. `moodle-sitemap` solves that by turning a real authenticated browser session into durable site-intelligence artifacts that downstream tools can inspect without replaying the live UI.

Today that means the project is especially useful for:

- identifying what authenticated pages exist for a given role
- understanding what a page appears to be for
- surfacing likely next navigation steps without clicking anything
- comparing visibility and affordances across admin, teacher, and student runs
- validating whether the saved graph is already good enough for representative Moodle tasks

## Current scope

Phase 1 currently does the following:

- runs a config-driven smoke test against a Moodle login flow
- runs a timestamped verification smoke+crawl workflow for regression checks
- runs a timestamped discovery crawl workflow for broader route discovery
- logs into a Moodle LMS with a username and password
- crawls authenticated pages on the same origin
- follows safe links only
- avoids logout and obviously destructive URLs
- avoids form submission
- normalizes and de-duplicates visited URLs
- stores a stable `normalized_url` per page record for canonical destination handling
- captures page metadata, discovered links, body classes, breadcrumbs, richer page affordances, and lightweight network activity
- emits a lightweight workflow edge layer between visited pages
- captures Moodle footer performance or debug information when present
- writes a top-level `sitemap.json` plus one JSON file per page
- classifies pages into a small Moodle-aware set of page types

Later Phase 2 additions build on that same crawl:

- structured affordance extraction
- workflow edges and `next_steps`
- safety metadata
- role-aware run comparison
- task-oriented validation over saved artifacts

Initial page types:

- `dashboard`
- `course_view`
- `course_edit`
- `course_switch_role`
- `activity_view`
- `activity_edit`
- `admin_search`
- `admin_category`
- `admin_setting_page`
- `admin_tool_page`
- `contact_site_support`
- `user_profile`
- `user_profile_edit`
- `user_preferences`
- `user_settings_page`
- `private_files`
- `content_bank_preferences`
- `messages`
- `message_preferences`
- `notifications`
- `calendar`
- `blog_page`
- `forum_user_page`
- `report_builder`
- `gradebook`
- `unknown`

`messages` means the main Moodle messaging interface at `message/index.php`.
`course_switch_role` means the course role-switching interface at `course/switchrole.php`.
`contact_site_support` means the contact site support form/page at `user/contactsitesupport.php`.
Role validation also exposed a distinct lower-privilege user/profile/preferences surface, so pages like `user/edit.php`, `user/contentbank.php`, `blog/*`, and `mod/forum/user.php` now classify explicitly instead of remaining generic `unknown`.
The admin surface is intentionally split into a few stable route-driven subtypes rather than one broad admin bucket.

## Non-goals

Phase 1 does not attempt to:

- submit forms
- mutate site state
- bypass Moodle permissions
- support every Moodle theme or login customization
- summarize pages with an LLM
- expose MCP integration
- store crawl state in SQLite
- provide deep plugin-specific Moodle semantics

## Safety assumptions

The crawler is intentionally conservative:

- it stays within the supplied site origin
- it ignores `mailto:`, `javascript:`, fragment-only links, and non-HTTP(S) links
- it skips URLs that look like logout or destructive actions
- it does not click buttons or submit forms as part of crawling
- it redacts obvious secrets from stored network data, including passwords, cookies, authorization headers, `sesskey`, tokens, and similar values

This tool still runs as an authenticated browser session. Use credentials with care and start with a low `--max-pages` value until you trust the target site.

## Install

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
playwright install chromium
```

## Prepare a Moodle site

Before your first crawl, prepare a Moodle instance that exposes representative pages, footer metrics, and useful debug information. This matters because the crawler can only classify and enrich what the site actually renders for the logged-in user.

Start with the dedicated setup guide:

- [Moodle site preparation guide](docs/moodle-site-preparation.md)

Recommended flow:

1. Install the CLI and Playwright browser runtime.
2. Prepare a Moodle site for authenticated crawling.
3. Run the smoke test to validate login and post-login capture.
4. Run a verification smoke+crawl when you want a preserved regression snapshot.
5. Run a broader discovery crawl when you want to surface new page families and route patterns.
6. Run a bounded crawl with a dedicated crawler account.
7. Inspect the generated JSON artifacts.

### Minimum useful test site

For phase 1, a good minimum setup is:

- a local, staging, QA, or disposable Moodle environment
- debugging enabled, with developer/debug messages visible
- performance info enabled in the footer
- one dedicated crawler account with site admin access for broad initial coverage
- 2 to 3 courses with sections or topics
- common activities such as assignment, quiz, forum, page, file, and URL
- a few enrolled users in different roles where practical
- a standard theme such as Boost or Classic

An empty Moodle site will still crawl, but it will produce a much less useful sitemap.

### Generated test content for validation

For local or disposable validation environments, Moodle's test-site generator is a practical way to expose more course and activity pages:

```bash
public/admin/tool/generator/cli/maketestsite.php --size S
```

This is useful because generated content:

- exposes more course and activity routes
- improves classifier validation coverage
- makes verification crawls more representative

Treat this as a dev/test workflow, not a production recommendation. The broader site-preparation guidance is in:

- [Moodle site preparation guide](docs/moodle-site-preparation.md)

## Usage

The workflows intentionally build on one another:

- `smoke` proves login, browser startup, and basic post-login capture
- `verify` produces a small, timestamped regression snapshot
- `discover` produces a broader but still bounded site-intelligence run
- `compare-runs` explains how two saved runs differ
- `validate-tasks` checks whether saved artifacts support representative tasks without executing them

### Smoke test

Create a local config file from the example:

```bash
cp config.example.toml config.toml
```

Example config:

```toml
[site]
url = "https://example.com"

[auth]
username = "admin"
password = "secret"

[browser]
engine = "chromium"
headless = true

[run]
role = "admin"
```

Run the smoke test:

```bash
moodle-sitemap smoke --config ./config.toml
```

What this proves:

- the config file is valid
- the selected Playwright browser can launch
- the crawler can reach the Moodle site
- login succeeds with the supplied credentials
- the tool can capture minimal post-login page metadata
- the run can be labeled with a role/profile such as `admin`, `teacher`, or `student`

Expected output:

```text
output/
  smoke-test.json
```

The smoke test is intentionally narrow. It is a reliability checkpoint before running a richer crawl.

### Verification run

Run a preserved verification workflow:

```bash
moodle-sitemap verify --config ./config.toml --max-pages 10
```

What this does:

- runs the smoke test first
- runs a small authenticated crawl with the same config
- writes the results into a timestamped, git-ignored run folder

Example output:

```text
verification-runs/
  2026-04-07T101530Z/
    smoke-test.json
    sitemap.json
    workflow-edges.json
    pages/
      0001-my.json
      ...
```

This is intended for regression checking over time, especially for canonical URL handling, footer parsing, and extraction behavior.

Verification and discovery crawls print lightweight progress lines in the CLI as pages are captured, for example:

```text
[16/40] 0016-course-view-php-id-4 course_view https://example.com/course/view.php?id=4
```

### Discovery crawl

Run a broader but still controlled discovery crawl:

```bash
moodle-sitemap discover --config ./config.toml --max-pages 200 --max-depth 4
```

What this does:

- runs a larger authenticated crawl budget than verification mode
- keeps the same safety guardrails as the normal crawler
- writes the crawl into a timestamped, git-ignored discovery folder
- writes a machine-readable `discovery-summary.json`
- writes a short human-readable `discovery-summary.md`
- writes `page-timings.json` and `timing-summary.json` for crawl timing analysis
- prints per-page crawl progress to the CLI

Example output:

```text
discovery-runs/
  2026-04-08T110000Z/
    sitemap.json
    workflow-edges.json
    page-timings.json
    timing-summary.json
    discovery-summary.json
    discovery-summary.md
    pages/
      0001-my.json
      ...
```

Discovery mode is for widening coverage, not for exhaustive or interaction-heavy crawling. It still:

- stays on the configured origin
- follows safe links only
- avoids logout and obvious destructive routes
- avoids form submission
- respects the configured page budget and depth cap

The discovery summary is meant to highlight what a larger crawl surfaced, including:

- total pages and page counts by type
- newly seen route families compared with the latest verification run
- query-heavy routes that may need future exclusions
- canonicalization events still worth reviewing
- slowest pages
- crawl timing totals and slowest route families
- remaining unknown or weakly classified pages

### Role-specific validation

Role-specific discovery runs are useful because Moodle navigation, visible pages, available actions, safety signals, and next-step suggestions can change materially by role.

For practical validation, keep one config per role and run the same discovery budget for each profile. For local test credentials, it is convenient to keep these temporary files under `/_smoke_test` so they stay git-ignored.

Example role configs:

```text
_smoke_test/
  admin-config.toml
  teacher-config.toml
  student-config.toml
```

Run the same crawl settings for all three roles so the differences are easier to interpret:

```bash
moodle-sitemap discover --config ./_smoke_test/admin-config.toml --max-pages 40 --max-depth 4
moodle-sitemap discover --config ./_smoke_test/teacher-config.toml --max-pages 40 --max-depth 4
moodle-sitemap discover --config ./_smoke_test/student-config.toml --max-pages 40 --max-depth 4
```

This helps validate:

- admin-only page visibility
- teacher vs student differences on course and participant pages
- reduced or safer affordances for lower-privilege roles
- workflow and `next_steps` differences across the same site
- where the current classifier or graph still needs role-sensitive refinement

### Full crawl

```bash
moodle-sitemap crawl \
  --site-url https://example.com \
  --username admin \
  --password secret \
  --output ./output \
  --max-pages 200 \
  --headless true
```

### Compare runs

Compare two saved crawl or discovery runs:

```bash
moodle-sitemap compare-runs \
  --left ./discovery-runs/2026-04-08T014634Z \
  --right ./discovery-runs/2026-04-08T014428Z
```

This writes a timestamped comparison artifact under `comparison-runs/` with:

- role-pair-specific JSON and Markdown files such as:
  - `role-compare-admin-vs-teacher.json`
  - `role-compare-admin-vs-teacher.md`

Example output:

```text
comparison-runs/
  2026-04-08T150000Z/
    role-compare-admin-vs-teacher.json
    role-compare-admin-vs-teacher.md
```

The comparison focuses on:

- page counts
- page-type count deltas
- pages visible in one run but not the other
- workflow edges visible in one run but not the other
- high-signal action differences on shared pages
- `next_steps` differences on shared pages
- safety/risk differences on shared pages

### Task validation

Task validation checks whether saved crawl artifacts are already good enough to support a small set of realistic Moodle tasks. It does not drive the browser. It evaluates saved page types, workflow edges, `next_steps`, affordances, and safety hints.

Run task validation against a saved run:

```bash
moodle-sitemap validate-tasks \
  --run ./discovery-runs/2026-04-08T230425Z \
  --tasks ./task-validation/tasks.json
```

This writes a timestamped result under `task-validation-runs/` with:

- `task-validation.json`
- `task-validation.md`

Example output:

```text
task-validation-runs/
  2026-04-09T110000Z/
    task-validation.json
    task-validation.md
```

Task validation is different from discovery and run comparison:

- discovery asks what pages and paths exist
- compare-runs asks how two saved runs differ
- task validation asks whether the current saved model is strong enough to support representative agent-facing tasks

Task validation also tries to surface the most relevant controls for the task instead of the first visible controls on the page. It ranks candidate affordances using page type, target route family, `likely_intent`, `importance_level`, form purpose, and alignment with the page's primary intent.

Each task result includes lightweight path-support hints such as:

- `best_path_confidence`
- `first_hop_quality`
- `key_affordance_relevance`

### Runtime-facing contract

For orchestration/runtime use, `agentic_sitemap` now adopts the canonical shared outer runtime schema owned by `agentic_devdocs`.

Supported commands:

- `runtime-query --json-contract`
  - `page` lookup by page URL, route, or page id against a saved run
  - `page_type` lookup against a saved run
  - `path` lookup between pages in a saved run
- `validate-tasks --json-contract`
  - returns task-validation results in the same outer contract envelope

The contract is intentionally narrow. It wraps existing saved sitemap/task-validation artifacts; it does not change crawling behavior or the human-oriented artifact formats. The shared outer envelope, shared provenance block, and shared diagnostics block follow the vendored canonical schema in [`schemas/shared_runtime_contract_v1.json`](/Users/mattp/projects/agentic_sitemap/schemas/shared_runtime_contract_v1.json). Sitemap keeps its own tool-specific payload inside `results[].content`.

Shared outer envelope:

```json
{
  "tool": "agentic_sitemap",
  "version": "v1",
  "query": "...",
  "normalized_query": "...",
  "intent": {
    "query_intent": "...",
    "task_intent": "...",
    "concept_families": []
  },
  "results": []
}
```

Contract rules:

- `tool`, `version`, `query`, `normalized_query`, `intent`, and `results` are always present.
- `results` is always a list, even when empty.
- every result always includes `id`, `type`, `rank`, `confidence`, `source`, `content`, and `diagnostics`
- the supported live contract modes are `runtime-query` with `page`, `page_type`, and `path`, plus `validate-tasks`; all are expected to emit the full outer envelope and full result object shape
- `source.heading_path` is always a list
- nullable provenance fields such as `source.url`, `source.canonical_url`, and `source.section_title` remain present as `null` when absent
- result ids are deterministic hashes derived from stable page/task/path identifiers rather than random values

Provenance semantics:

- `source.name`: stable source label, currently `moodle_site`
- `source.type`: currently `site_crawl`
- `source.url`: original page URL when available
- `source.canonical_url`: normalized canonical page URL when available
- `source.path`: route path or path-with-query used for traceability
- `source.document_title`: page title when available
- `source.section_title`: currently `null` for sitemap results
- `source.heading_path`: currently `[]` for sitemap results

Conformance validation:

- the vendored canonical schema artifact is checked in at [`schemas/shared_runtime_contract_v1.json`](/Users/mattp/projects/agentic_sitemap/schemas/shared_runtime_contract_v1.json)
- runtime contract tests validate the supported live `--json-contract` commands against the aligned shared model
- sitemap-specific `results[].content` remains tool-specific; only the shared outer envelope and shared result/source/diagnostics structure are standardized

Confidence semantics are intentionally coarse:

- `high`: exact or strongest runtime match
- `medium`: useful but broader or less direct match
- `low`: weak fallback or contextual result

Page/context example:

```bash
moodle-sitemap runtime-query \
  --run ./discovery-runs/2026-04-09T025735Z \
  --lookup-mode page \
  --query https://webserver/user/preferences.php \
  --json-contract
```

Workflow/path example:

```bash
moodle-sitemap runtime-query \
  --run ./discovery-runs/2026-04-09T025735Z \
  --lookup-mode path \
  --from-page dashboard \
  --to-page user_preferences \
  --json-contract
```

Task-validation example:

```bash
moodle-sitemap validate-tasks \
  --run ./discovery-runs/2026-04-09T025735Z \
  --tasks ./task-validation/tasks.json \
  --json-contract
```

## Architecture and maintenance notes

For a maintainer-oriented walkthrough of module boundaries, artifact lifecycle, invariants, extension rules, and testing strategy, see:

- [Architecture and developer guide](docs/architecture.md)

## Output layout

Example output:

```text
output/
  smoke-test.json
  sitemap.json
  workflow-edges.json
  pages/
    0001-root.json
    0002-course-view-id-2.json
    0003-mod-forum-view-id-14.json
```

`sitemap.json` contains the site manifest, a compact summary section, and page entries for all visited pages. Each page file contains the same page-record schema as the manifest entry for that page.

Discovery runs also include:

- `discovery-summary.json` for machine-readable post-run analysis
- `discovery-summary.md` for a short human-readable review
- `workflow-edges.json` for page-to-page workflow relationships

`smoke-test.json` contains a single post-login checkpoint record with `site_url`, `browser`, URLs before and after login, title, status when available, body metadata, breadcrumbs, timestamp, and `login_succeeded`.

Example `smoke-test.json` shape:

```json
{
  "site_url": "https://example.com/",
  "role_profile": "admin",
  "browser": "chromium",
  "initial_url": "https://example.com/",
  "final_url": "https://example.com/my",
  "page_title": "Dashboard | Moodle Demo",
  "http_status": 200,
  "body_id": "page-my-index",
  "body_classes": ["path-my", "pagelayout-mydashboard"],
  "breadcrumbs": [],
  "login_succeeded": true,
  "captured_at": "2026-04-07T10:15:30Z"
}
```

Each crawled page record includes:

- `page_id`: the stable per-run page ID used for the JSON filename
- `url`: the requested URL
- `final_url`: the final browser URL after navigation
- `normalized_url`: the canonicalized crawl URL used for de-duplication and stable reporting
- `primary_page_intent`: the top-level derived intent used by graph ranking and task validation
- `primary_actions`: the top few action labels supporting that intent
- `task_relevance_score`: a compact page-purpose strength hint
- `affordances`: structured agent-usable UI understanding without interaction
- `task_summary`: compact page-purpose hints derived from the strongest visible affordances and page context
- `next_steps`: compact likely next-page candidates derived from the workflow edge layer

### Manifest summary

`sitemap.json` also includes a compact `summary` object with:

- `total_pages`
- `unknown_pages`
- `workflow_edge_count`
- `page_type_counts`
- `crawl_started_at`
- `crawl_finished_at`

Example `sitemap.json` summary shape:

```json
{
  "summary": {
    "total_pages": 10,
    "unknown_pages": 4,
    "page_type_counts": {
      "dashboard": 1,
      "course_view": 0,
      "activity_view": 0,
      "admin_search": 1,
      "admin_setting_page": 1,
      "user_profile": 1,
      "gradebook": 1,
      "unknown": 5
    },
    "crawl_started_at": "2026-04-07T10:15:30Z",
    "crawl_finished_at": "2026-04-07T10:16:02Z"
  }
}
```

## Stored data

Each page record includes:

- stable `page_id`
- canonical `normalized_url` alongside requested and final URLs
- final URL and requested URL
- page title
- page type
- role-aware safety metadata
- referrer
- HTTP status when Playwright exposes it
- body id and classes
- breadcrumbs
- affordances for actions, navigation, forms, editors, file inputs, filters, tabs, tables, lists, and sections
- affordance importance and likely-intent hints for actions, navigation, and forms
- a compact page-level `task_summary`
- discovered links
- conservative safety hints on actions and forms
- next-step hints derived from page-to-page workflow edges
- Moodle footer or debug details when present
- raw footer text plus conservative structured parsing for current Moodle performance strings when available
- redacted network activity observed during page load

### Workflow edges

The crawler also writes `workflow-edges.json`, which captures likely page-to-page relationships such as:

- dashboard to course navigation
- course pages to related pages or activities
- preference pages to more specific preference pages
- admin pages to deeper admin pages
- admin search and category hubs to more specific settings and tool pages

This is different from raw discovered links:

- discovered links are just URLs found on a page
- workflow edges are filtered, typed relationships between visited pages
- edges include the source affordance label or kind when known
- edges also include a weight and relevance hint so downstream tools can separate task-bearing paths from generic site navigation
- admin-heavy runs should now surface more specific admin page families and clearer configuration paths

Edge types stay intentionally small:

- `navigation`
- `parent_child`
- `settings`
- `edit`
- `preferences`
- `activity`
- `admin`
- `related`

Each workflow edge also carries a separate weighting layer:

- `edge_weight`: `high`, `medium`, or `low`
- `edge_relevance`: `task`, `support`, `navigation`, or `contextual`
- `source_affordance_importance`: how prominent the originating control looked
- `reason_hint`: a short explanation of why the edge was weighted that way

The weighting is intentionally conservative:

- specific admin search/category to setting/tool pages should usually rank above broad admin hubs
- course and preference configuration paths should rank above generic site navigation
- repeated calendar variants, discovered-only admin links, and generic nav clusters should stay lower-value

The important distinction is:

- raw discovered links tell you that one page referenced another URL
- workflow edges tell you that a visible page control likely leads to another visited page
- weighted workflow edges help you focus on likely task progression instead of every navigational hop
- weaker fallback edges are suppressed when a stronger explicit path already exists between the same two pages
- repetitive weak admin or calendar navigation can be compressed into background clusters instead of staying as many first-class edges

### Affordance importance and likely intent

Action, navigation, and form affordances now include lightweight importance and intent hints such as:

- `importance_level`: `primary`, `secondary`, or `tertiary`
- `likely_intent`: values like `create`, `edit`, `save`, `search`, `configure`, `message`, `upload`, `view`, or `unknown`
- `prominence_score` on actions
- `central_to_page` and `likely_mutation_strength` on forms

These are deterministic heuristics based on visible labels, classes, button types, form structure, and route shape. They are meant to improve agent reasoning, not replace human review.

### Primary page intent

Each page record includes a top-level `primary_page_intent` hint, with the same value also preserved under `task_summary.primary_page_intent`. This is a compact best-effort signal for what the page is mainly for, using cues such as:

- page type
- prominent actions
- dominant form purpose
- navigation and tab context
- title, body id, and breadcrumb hints

Typical values include `navigate`, `configure`, `edit`, `search`, `message`, `report`, `upload`, `view`, or `unknown`.

This value is used to make `next_steps` cleaner and more task-aligned, and it is serialized directly on the page record because task validation and downstream packaging rely on it. It is still heuristic, not a guarantee.

### Background navigation clusters

When a page emits many low-value weak edges from repetitive families, the crawler can compress them into `background_navigation_clusters` instead of keeping each weak edge as a first-class graph edge.

These clusters are used for things like:

- repeated admin navigation spill
- repeated `/admin/tool` or `/admin/settings.php` background links
- repeated calendar query variants

Each cluster is explicit and inspectable. It summarizes:

- the source page
- the compressed family key
- how many weak edges were grouped
- representative targets
- the shared low-value relevance and reason

This is meant to preserve awareness of background navigation while keeping the main graph focused on stronger task and support paths.

### Affordance safety hints

Action and form affordances include conservative heuristic safety hints:

- `inspect_only`: appears suitable for read-only inspection or navigation
- `navigation_safe`: looks like non-mutating navigation
- `likely_mutating`: looks likely to change site state
- `likely_destructive`: looks likely to delete, remove, purge, or otherwise destructively mutate state
- `requires_confirmation_likely`: looks likely to trigger a confirmation step

These are hints, not guarantees. They are meant to help downstream tools reason about risk without clicking anything.

### Page safety metadata

Each page record also includes a page-level `safety` summary with heuristics such as:

- `page_risk_level`
- `contains_mutating_actions`
- `contains_destructive_actions`
- `likely_requires_confirmation`
- `contains_sesskey_backed_actions`

These aggregate the action and form hints into a simpler page-wide view. They are still heuristics, not hard guarantees.

Example page record shape:

```json
{
  "page_id": "0001-my",
  "url": "https://example.com/",
  "normalized_url": "https://example.com/my",
  "final_url": "https://example.com/my",
  "title": "Dashboard | Moodle Demo",
  "page_type": "dashboard",
  "primary_page_intent": "navigate",
  "primary_actions": ["Course 1", "Course 2", "Calendar"],
  "task_relevance_score": 76,
  "safety": {
    "page_risk_level": "medium",
    "contains_mutating_actions": true,
    "contains_destructive_actions": false,
    "likely_requires_confirmation": false,
    "contains_sesskey_backed_actions": true,
    "navigation_safe_action_count": 12,
    "mutating_action_count": 1
  },
  "body_id": "page-my-index",
  "body_classes": ["path-my", "pagelayout-mydashboard"],
  "breadcrumbs": [],
  "next_steps": [
    {
      "page_id": "0016-course-view-php-id-4",
      "target_url": "https://example.com/course/view.php?id=4",
      "target_page_type": "course_view",
      "edge_type": "navigation",
      "edge_weight": "high",
      "edge_relevance": "task",
      "label": "Course 1",
      "confidence": 0.95,
      "notes": "dashboard-to-course"
    }
  ],
  "task_summary": {
    "primary_page_intent": "navigate",
    "primary_actions": ["Course 1", "Course 2", "Calendar"],
    "task_relevance_score": 76
  },
  "affordances": {
    "actions": [
      {
        "label": "Turn editing on",
        "url": null,
        "element_type": "button",
        "action_key": "turn-editing-on",
        "importance_level": "primary",
        "likely_intent": "edit",
        "prominence_score": 95,
        "in_primary_region": true,
        "in_menu_or_overflow": false,
        "is_primary": true,
        "disabled": false,
        "safety": {
          "inspect_only": false,
          "navigation_safe": false,
          "likely_mutating": true,
          "likely_destructive": false,
          "requires_confirmation_likely": false
        }
      }
    ],
    "navigation": [],
    "forms": [
      {
        "id": null,
        "method": "post",
        "action": "https://example.com/editmode.php",
        "fields": [
          {
            "name": "setmode",
            "label": "Turn editing on",
            "field_type": "hidden",
            "visible": false,
            "required": false
          }
        ],
        "submit_controls": [],
        "purpose": "edit_form",
        "importance_level": "secondary",
        "likely_intent": "edit",
        "likely_mutation_strength": "low",
        "central_to_page": false,
        "safety": {
          "inspect_only": false,
          "navigation_safe": false,
          "likely_mutating": true,
          "likely_destructive": false,
          "requires_confirmation_likely": false
        }
      }
    ],
    "editors": {
      "has_tinymce": false,
      "has_atto": false,
      "has_textarea": true
    },
    "file_inputs": [],
    "filters": [],
    "tabs": [],
    "tables": [],
    "lists": [],
    "sections": []
  },
  "footer": null,
  "discovered_links": [],
  "network": []
}
```

## Design notes

The package is split into focused modules:

- browser lifecycle
- authentication
- crawl orchestration
- URL discovery and normalization
- DOM extraction
- footer parsing
- network redaction
- page classification
- JSON storage

The structure is meant to stay stable as the project grows into a broader Moodle-aware site mapping toolkit for agentic and browser-assisted tooling.

## Testing

Run the full suite:

```bash
pytest
```

Useful narrower subsets during development:

```bash
pytest tests/test_page_type.py tests/test_workflow.py
pytest tests/test_task_validation.py tests/test_compare_runs.py
pytest tests/test_schema.py tests/test_discovery.py
```

This repo includes:

- config loading and browser-engine validation
- URL normalization
- canonical destination de-duplication
- Moodle page classification
- footer or debug parsing
- body and breadcrumb normalization
- network redaction and recorder behavior
- workflow derivation, weighting, de-noising, and compression
- comparison and task-validation logic
- artifact serialization contracts and regression cases

Browser end-to-end testing is intentionally minimal in this phase. Logic that would be hard to test through Playwright is isolated into small pure functions.

## Current limitations

The project is intentionally conservative:

- it does not execute workflows or submit forms
- safety hints are heuristic and may be noisy on complex admin pages
- some page families still use practical buckets such as `user_settings_page` rather than many micro-types
- weaker social surfaces such as forum-user pages are now discoverable, but still less strongly supported than admin, course, and preference flows
- discovery quality still depends on what the selected role can actually see

## Further reading

- [Preparing a Moodle site for crawling](docs/moodle-site-preparation.md)
- [Verification runs](docs/verification-runs.md)
- [Architecture and developer guide](docs/architecture.md)
