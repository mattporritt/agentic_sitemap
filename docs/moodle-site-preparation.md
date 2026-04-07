# Preparing a Moodle Site for Crawling

This guide explains how to prepare a Moodle LMS instance so `moodle-sitemap` can produce a more useful authenticated sitemap and richer page records.

The recommendations here are aimed at development, staging, QA, and disposable test environments. They are not a blanket recommendation for production.

## Why site preparation matters

`moodle-sitemap` only captures what a logged-in browser session can actually see. If the site has no representative courses, no visible debug or performance information, and a heavily customized theme, the crawl output will still be valid, but it will be much less informative.

Preparing the site improves:

- page type coverage such as dashboard, course, activity, admin, profile, and gradebook pages
- form and editor detection
- breadcrumb and body-class extraction
- footer metric capture
- visibility into AJAX and XHR behavior during page load
- later browser-assisted or agentic analysis built on the sitemap output

## Use a safe environment first

Start in a local, staging, QA, or disposable test environment.

Do not start on production if you can avoid it. The settings recommended in this guide may expose extra diagnostics, warnings, and performance details that are useful for testing but inappropriate for a live site.

Use the crawler only on systems you are authorized to access.

## Recommended baseline

If you want a short checklist, use this as the minimum useful test site profile:

- a non-production Moodle environment
- standard theme such as Boost or Classic
- one dedicated crawler account
- site admin privileges for the first broad crawl
- debugging enabled
- debug messages displayed
- performance info visible in the footer
- 2 to 3 representative courses
- common activity types: assignment, quiz, forum, page, file, URL
- some enrolled users in different roles where practical

## Debugging and developer-friendly settings

### Why these settings help

Debugging and performance settings make Moodle render information that the crawler can capture from the page footer and visible page output. This can include:

- page generation time
- memory use
- database query counts where configured
- developer warnings and notices
- richer clues about page behavior and server-side rendering issues

### Core debugging settings

In standard Moodle admin screens, the usual path is:

- `Site administration > Development > Debugging`

Exact labels and menu placement can vary by Moodle version and theme, but the common targets are:

- set debug messages to `DEVELOPER` when you are preparing a dev or QA crawl environment
- enable display of debug messages so warnings and notices are rendered in-page
- enable performance information so footer metrics are visible

These settings are documented in MoodleDocs:

- [Debugging](https://docs.moodle.org/en/Debugging)

### Footer performance information

Moodle can render performance information in the footer of standard themes and some other themes. This is useful to `moodle-sitemap` because the crawler stores footer/debug data when it is present.

Typical footer output may include:

- page generation time
- memory usage
- CPU or load details depending on configuration
- cache information
- database query counts when additional performance constants are enabled

The Moodle debugging docs also note that some database-query performance counters require `config.php` settings such as `MDL_PERF`, `MDL_PERFDB`, `MDL_PERFTOLOG`, and `MDL_PERFTOFOOT`. Treat those as dev-environment settings, not defaults for a live site.

### Other useful dev-oriented settings

Depending on your workflow, these may also help:

- developer mode features that expose test generators or additional diagnostics
- visible error output during page rendering
- cache purging after theme or plugin changes so the crawl sees the current UI

If you are working from the server shell, Moodle documents general CLI administration entry points here:

- [Administration via command line](https://docs.moodle.org/en/CLI_scripts)

## Theme and UI considerations

For early crawler validation, prefer a standard core theme where possible.

MoodleDocs identifies Boost and Classic as standard themes in recent versions:

- [Standard themes](https://docs.moodle.org/en/Standard_themes)
- [Boost theme](https://docs.moodle.org/en/Boost_theme)

Why this matters:

- custom themes often change layout structure, navigation placement, and selectors
- custom themes may hide or restyle breadcrumbs, menus, or footer regions
- crawl output may vary significantly across themes even on the same Moodle version

Recommendation:

- start with Boost or Classic to establish a known-good crawl baseline
- test custom themes afterward and compare crawl output rather than assuming parity

## Authentication and crawler account setup

### Use a dedicated crawler account

Create a dedicated user for crawling instead of reusing a personal admin account.

This makes it easier to:

- rotate credentials
- understand what the crawler can see
- limit or expand permissions intentionally
- separate crawl traffic from normal administrator activity

### Use admin access first, then narrow later

For early testing, a site admin account is often the best choice because it exposes:

- admin settings pages
- broader navigation
- more representative forms and management screens
- more complete footer/debug output

Later, it is worth running role-specific crawls as separate users, for example:

- admin
- teacher
- student

Those role-specific crawls can reveal gaps in navigation, permissions, and page visibility that an admin-only crawl would miss.

### Permission cautions

Be careful with:

- real user data
- production content
- privileged admin views
- pages that expose debug output or internal warnings

The crawler stores structured page and network metadata. Even with redaction of obvious secrets, you should assume the output may still contain operationally sensitive information.

## Representative site content

An empty Moodle site is not very useful for crawl enrichment.

To produce meaningful output, create enough content to expose common Moodle page types and UI patterns. At minimum, prepare:

- one or more courses
- sections or topics inside each course
- common activity types such as assignment, quiz, forum, page, file, and URL
- some enrolled users in different roles where practical
- profile pages, dashboard content, and gradebook-visible activity where relevant

Why this helps:

- page classification works better when real Moodle page patterns are present
- breadcrumbs and body classes become more representative
- form extraction becomes more useful
- editor detection is more likely to find TinyMCE, Atto, or textarea-based content areas
- network capture becomes more representative when activities and dynamic blocks are present

## Using Moodle CLI and admin tooling to seed content

Moodle has a mix of UI-based admin tools and CLI scripts. Exact options vary by version, and not every content-seeding workflow is equally automated across releases.

The safest way to think about this is:

- use Moodle’s standard admin tools when you need predictable setup across versions
- use CLI scripts where Moodle clearly documents them
- avoid assuming every content operation has a stable CLI equivalent

### Common approaches

#### 1. Generate a test site through the developer generator

If you have shell access and are in a dev-style environment, the most practical documented option is Moodle’s test site generator:

- [Test site generator](https://docs.moodle.org/en/Test_site_generator)

Example:

```bash
cd /path/to/moodle
php admin/tool/generator/cli/maketestsite.php --size=S
```

Equivalent project-local path example:

```bash
public/admin/tool/generator/cli/maketestsite.php --size S
```

This tool is explicitly for developer use, requires developer debugging mode, and should not be used on a live site. It is a good fit when you want a quickly populated Moodle instance with courses, users, and enrolments.

#### 2. Use upload users for accounts and enrolment-oriented setup

Moodle documents both UI-based and CLI-assisted user upload workflows:

- [Upload users](https://docs.moodle.org/en/Upload_users)

In supported versions, MoodleDocs notes a CLI script:

```bash
php admin/tool/uploaduser/cli/uploaduser.php --help
```

This is useful when you want repeatable creation of:

- crawler accounts
- teacher and student users
- enrolment-ready user sets

#### 3. Use upload courses through admin tooling

Moodle also documents bulk course creation through the admin UI:

- [Upload courses](https://docs.moodle.org/30/en/Upload_courses)

That workflow is commonly used to create several courses from CSV. It is practical when you want predictable course shells and do not need a full synthetic test-site generator run.

### Practical advice

For most teams, a reasonable setup order is:

1. Enable developer/debug settings in a non-production environment.
2. Use the test site generator if you need a fast baseline dataset.
3. Add or adjust users through upload users if you need named crawler, teacher, or student accounts.
4. Add a few curated courses and activities manually so the dataset reflects the workflows you actually care about.

That last step matters. Generated data is useful, but hand-curated activities often produce more meaningful crawl output for your own Moodle deployment.

## Performance footer data

Moodle performance footer output is a compact summary that can appear in the page footer when enabled. Depending on site configuration and theme support, it may include:

- generation time
- memory usage
- cache information
- database query counts

This is useful to `moodle-sitemap` because the page records can capture footer/debug text and parse stable metrics when they are present.

Important caveats:

- not every site enables footer performance info
- some themes may hide or alter it
- some metrics require additional `config.php` settings
- it should generally only be enabled in safe environments

## AJAX and network visibility

Modern Moodle pages often depend on JavaScript, fetch, and XHR requests.

This matters for crawl quality because:

- some blocks and page widgets load data after the initial document request
- course and activity pages may call background endpoints during load
- richer content usually produces richer network traces

At the same time, a basic crawl has limits:

- some network activity only appears after user interaction
- some endpoints only appear for specific roles or plugins
- some AJAX behaviors depend on expanded drawers, opened modals, or editing mode

So the crawler can capture meaningful network behavior during page load, but it should not be treated as a complete interaction trace of everything the site can do.

## Tradeoffs and admin implications

When you enable the settings in this guide, you are deliberately trading some operational caution for better diagnostics.

Benefits:

- richer crawl output
- more footer metrics
- clearer warnings and page diagnostics
- better visibility into Moodle page structure and behavior

Costs:

- more internal information may be exposed in-page
- performance overhead may increase
- admins may see noisier pages
- generated test data can consume storage and clutter the environment

Use these settings and tools intentionally, and roll them back when you no longer need them.

## Suggested preparation workflow

If you want a concrete sequence:

1. Create or choose a non-production Moodle environment.
2. Switch to a standard theme such as Boost or Classic.
3. Enable debugging, display debug messages, and footer performance info.
4. Create a dedicated crawler account.
5. Give that account site admin access for the first broad crawl.
6. Seed the site with courses, sections, activities, and role diversity.
7. Run a small crawl first, for example `--max-pages 25`.
8. Review the output and then expand the crawl budget.

## After preparation

Once the site is ready, run the crawler from this project:

```bash
moodle-sitemap crawl \
  --site-url https://example.com \
  --username crawler-admin \
  --password secret \
  --output ./output \
  --max-pages 200 \
  --headless true
```

Then inspect:

- `output/sitemap.json`
- `output/pages/*.json`

If the results are thinner than expected, the usual causes are:

- not enough representative content
- a role with limited visibility
- a custom theme changing page structure
- debug or footer performance settings not enabled
- a site where meaningful network behavior only appears after user interaction
