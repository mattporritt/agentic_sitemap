# moodle-sitemap

`moodle-sitemap` is a phase 1 Moodle-aware authenticated sitemap builder for browser-assisted tooling. It logs into a Moodle LMS with supplied credentials, crawls a bounded set of same-origin pages using a real browser, and writes a structured JSON sitemap to disk.

This first version is intentionally narrow. The goal is to produce a dependable crawl artifact that future tooling can build on, not to solve every Moodle automation problem in one go.

## Why this exists

Moodle sites are heavily authenticated, dynamic, and often shaped by role-based navigation, AJAX flows, and LMS-specific page patterns. A requests-only crawler tends to miss too much. This project uses Playwright so the crawler behaves more like a real user session while still keeping the scope production-sensible.

This project is also intentionally AI agnostic. The core crawler does not depend on LLMs, agent frameworks, LangChain, MCP, or SQLite.

## Current scope

Phase 1 currently does the following:

- runs a config-driven smoke test against a Moodle login flow
- runs a timestamped verification smoke+crawl workflow for regression checks
- logs into a Moodle LMS with a username and password
- crawls authenticated pages on the same origin
- follows safe links only
- avoids logout and obviously destructive URLs
- avoids form submission
- normalizes and de-duplicates visited URLs
- stores a stable `normalized_url` per page record for canonical destination handling
- captures page metadata, discovered links, body classes, breadcrumbs, forms, editor presence, labels, and lightweight network activity
- captures Moodle footer performance or debug information when present
- writes a top-level `sitemap.json` plus one JSON file per page
- classifies pages into a small Moodle-aware set of page types

Initial page types:

- `dashboard`
- `course_view`
- `course_edit`
- `course_switch_role`
- `activity_view`
- `activity_edit`
- `admin_settings`
- `contact_site_support`
- `user_profile`
- `user_preferences`
- `private_files`
- `messages`
- `message_preferences`
- `notifications`
- `calendar`
- `report_builder`
- `gradebook`
- `unknown`

`messages` means the main Moodle messaging interface at `message/index.php`.
`course_switch_role` means the course role-switching interface at `course/switchrole.php`.
`contact_site_support` means the contact site support form/page at `user/contactsitesupport.php`.

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
5. Run a bounded crawl with a dedicated crawler account.
6. Inspect the generated JSON artifacts.

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
    pages/
      0001-my.json
      ...
```

This is intended for regression checking over time, especially for canonical URL handling, footer parsing, and extraction behavior.

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

## Output layout

Example output:

```text
output/
  smoke-test.json
  sitemap.json
  pages/
    0001-root.json
    0002-course-view-id-2.json
    0003-mod-forum-view-id-14.json
```

`sitemap.json` contains the site manifest, a compact summary section, and page entries for all visited pages. Each page file contains the same page-record schema as the manifest entry for that page.

`smoke-test.json` contains a single post-login checkpoint record with `site_url`, `browser`, URLs before and after login, title, status when available, body metadata, breadcrumbs, timestamp, and `login_succeeded`.

Example `smoke-test.json` shape:

```json
{
  "site_url": "https://example.com/",
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

### Manifest summary

`sitemap.json` also includes a compact `summary` object with:

- `total_pages`
- `unknown_pages`
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
      "admin_settings": 2,
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
- referrer
- HTTP status when Playwright exposes it
- body id and classes
- breadcrumbs
- forms
- editors
- visible links
- visible buttons
- discovered links
- forms with method, action, and field names
- Moodle footer or debug details when present
- raw footer text plus conservative structured parsing for current Moodle performance strings when available
- redacted network activity observed during page load

Example page record shape:

```json
{
  "page_id": "0001-my",
  "url": "https://example.com/",
  "normalized_url": "https://example.com/my",
  "final_url": "https://example.com/my",
  "title": "Dashboard | Moodle Demo",
  "page_type": "dashboard",
  "body_id": "page-my-index",
  "body_classes": ["path-my", "pagelayout-mydashboard"],
  "breadcrumbs": [],
  "forms": [],
  "editors": {
    "has_tinymce": false,
    "has_atto": false,
    "has_textarea": true
  },
  "links": [],
  "buttons": [],
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

This repo includes unit tests for:

- config loading and browser-engine validation
- URL normalization
- canonical destination de-duplication
- Moodle page classification
- footer or debug parsing
- body and breadcrumb normalization
- network redaction and recorder behavior

Browser end-to-end testing is intentionally minimal in this phase. Logic that would be hard to test through Playwright is isolated into small pure functions.

## Further reading

- [Preparing a Moodle site for crawling](docs/moodle-site-preparation.md)
- [Verification runs](docs/verification-runs.md)
