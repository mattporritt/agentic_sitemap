# Verification Runs

`moodle-sitemap` includes a narrow verification workflow that runs:

1. a config-driven smoke test
2. a small authenticated crawl

The output is written to a timestamped, git-ignored folder so you can keep successive runs for comparison.

## Command

```bash
moodle-sitemap verify --config ./config.toml --max-pages 10
```

## Output layout

```text
verification-runs/
  2026-04-07T101530Z/
    smoke-test.json
    sitemap.json
    pages/
      0001-my.json
      ...
```

## Why this exists

Verification runs are meant to catch regressions in:

- login behavior
- canonical URL handling and de-duplication
- footer parsing
- basic Moodle extraction signals such as body classes and breadcrumbs
- lightweight network capture

They are intentionally small enough to rerun often, but rich enough to expose correctness issues like duplicate canonical pages.
