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
- `activity_view`
- `admin_settings`
- `user_profile`
- `gradebook`
- `unknown`

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

`sitemap.json` contains the site manifest and summary of all visited pages. Each page file contains the full structured record for a single visited page.

`smoke-test.json` contains a single post-login checkpoint record with the configured site URL, browser engine, URLs before and after login, title, status when available, body metadata, breadcrumbs, timestamp, and `login_succeeded`.

Each crawled page record includes:

- `url`: the requested URL
- `final_url`: the final browser URL after navigation
- `normalized_url`: the canonicalized crawl URL used for de-duplication and stable reporting

## Stored data

Each page record includes:

- normalized URL and final URL
- canonical `normalized_url` alongside requested and final URLs
- page title
- page type
- referrer
- HTTP status when Playwright exposes it
- discovered links
- body id and classes
- breadcrumbs
- visible buttons and links
- forms with method, action, and field names
- editor hints such as TinyMCE, Atto, or plain textarea presence
- Moodle footer or debug details when present
- raw footer text plus conservative structured parsing for current Moodle performance strings when available
- redacted network activity observed during page load

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
