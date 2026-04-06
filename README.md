# moodle-sitemap

`moodle-sitemap` is a phase 1 Moodle-aware authenticated sitemap builder for browser-assisted tooling. It logs into a Moodle LMS with supplied credentials, crawls a bounded set of same-origin pages using a real browser, and writes a structured JSON sitemap to disk.

This first version is intentionally narrow. The goal is to produce a dependable crawl artifact that future tooling can build on, not to solve every Moodle automation problem in one go.

## Why this exists

Moodle sites are heavily authenticated, dynamic, and often shaped by role-based navigation, AJAX flows, and LMS-specific page patterns. A requests-only crawler tends to miss too much. This project uses Playwright so the crawler behaves more like a real user session while still keeping the scope production-sensible.

This project is also intentionally AI agnostic. The core crawler does not depend on LLMs, agent frameworks, LangChain, MCP, or SQLite.

## Current scope

Phase 1 currently does the following:

- logs into a Moodle LMS with a username and password
- crawls authenticated pages on the same origin
- follows safe links only
- avoids logout and obviously destructive URLs
- avoids form submission
- normalizes and de-duplicates visited URLs
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

## Usage

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
  sitemap.json
  pages/
    0001-root.json
    0002-course-view-id-2.json
    0003-mod-forum-view-id-14.json
```

`sitemap.json` contains the site manifest and summary of all visited pages. Each page file contains the full structured record for a single visited page.

## Stored data

Each page record includes:

- normalized URL and final URL
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

- URL normalization
- Moodle page classification
- footer or debug parsing

Browser end-to-end testing is intentionally minimal in this phase. Logic that would be hard to test through Playwright is isolated into small pure functions.
