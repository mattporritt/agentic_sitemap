# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

"""Lightweight crawl timing aggregation helpers.

The crawler writes raw per-page timing records and one run-level summary. This
module keeps the aggregation logic pure and easy to test so future performance
passes can reason about the current serial design before attempting
concurrency.
"""

from collections import defaultdict
from pathlib import Path
from statistics import median
from urllib.parse import urlparse

from moodle_sitemap.models import CrawlTimingSummary, PageTimingRecord


def route_family(url: str) -> str:
    """Group a URL into a compact path family for timing aggregation."""

    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if not parts:
        return "/"
    return "/" + "/".join(parts[:2])


def build_crawl_timing_summary(
    *,
    run_dir: str | Path,
    page_timings: list[PageTimingRecord],
    total_run_duration_seconds: float,
    crawl_loop_duration_seconds: float,
    workflow_derivation_duration_seconds: float = 0.0,
    manifest_write_duration_seconds: float = 0.0,
    workflow_write_duration_seconds: float = 0.0,
    timing_summary_generation_duration_seconds: float = 0.0,
) -> CrawlTimingSummary:
    """Aggregate per-page timings into one machine-readable run summary."""

    durations = [page.total_duration_seconds for page in page_timings]
    page_stage_totals = {
        "navigation_duration_seconds": round(sum(page.navigation_duration_seconds for page in page_timings), 6),
        "settle_duration_seconds": round(sum(page.settle_duration_seconds for page in page_timings), 6),
        "extraction_duration_seconds": round(sum(page.extraction_duration_seconds for page in page_timings), 6),
        "write_duration_seconds": round(sum(page.write_duration_seconds for page in page_timings), 6),
        "total_page_duration_seconds": round(sum(durations), 6),
    }
    run_stage_totals = {
        "crawl_loop_duration_seconds": round(crawl_loop_duration_seconds, 6),
        "workflow_derivation_duration_seconds": round(workflow_derivation_duration_seconds, 6),
        "manifest_write_duration_seconds": round(manifest_write_duration_seconds, 6),
        "workflow_write_duration_seconds": round(workflow_write_duration_seconds, 6),
        "timing_summary_generation_duration_seconds": round(
            timing_summary_generation_duration_seconds, 6
        ),
    }

    family_totals: dict[str, list[float]] = defaultdict(list)
    for page in page_timings:
        family_totals[page.route_family].append(page.total_duration_seconds)

    slowest_pages = [
        {
            "page_id": page.page_id,
            "normalized_url": page.normalized_url,
            "page_type": page.page_type,
            "total_duration_seconds": round(page.total_duration_seconds, 6),
            "navigation_duration_seconds": round(page.navigation_duration_seconds, 6),
            "settle_duration_seconds": round(page.settle_duration_seconds, 6),
            "extraction_duration_seconds": round(page.extraction_duration_seconds, 6),
            "write_duration_seconds": round(page.write_duration_seconds, 6),
        }
        for page in sorted(page_timings, key=lambda item: item.total_duration_seconds, reverse=True)[:10]
    ]
    slowest_extraction_pages = [
        {
            "page_id": page.page_id,
            "normalized_url": page.normalized_url,
            "page_type": page.page_type,
            "extraction_duration_seconds": round(page.extraction_duration_seconds, 6),
        }
        for page in sorted(page_timings, key=lambda item: item.extraction_duration_seconds, reverse=True)[:10]
    ]
    slowest_route_families = [
        {
            "route_family": family,
            "page_count": len(values),
            "average_duration_seconds": round(sum(values) / len(values), 6),
            "total_duration_seconds": round(sum(values), 6),
        }
        for family, values in sorted(
            family_totals.items(),
            key=lambda item: (sum(item[1]) / len(item[1]), sum(item[1])),
            reverse=True,
        )[:10]
    ]

    return CrawlTimingSummary(
        run_dir=str(run_dir),
        total_run_duration_seconds=round(total_run_duration_seconds, 6),
        crawl_loop_duration_seconds=round(crawl_loop_duration_seconds, 6),
        page_count=len(page_timings),
        average_page_duration_seconds=round(sum(durations) / len(durations), 6) if durations else 0.0,
        median_page_duration_seconds=round(median(durations), 6) if durations else 0.0,
        page_stage_totals=page_stage_totals,
        run_stage_totals=run_stage_totals,
        slowest_pages=slowest_pages,
        slowest_extraction_pages=slowest_extraction_pages,
        slowest_route_families=slowest_route_families,
    )
