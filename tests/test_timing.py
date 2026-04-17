# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from moodle_sitemap.models import PageTimingRecord
from moodle_sitemap.timing import build_crawl_timing_summary, route_family


def test_route_family_groups_first_two_path_segments() -> None:
    assert route_family("https://example.com/admin/tool/uploaduser/index.php") == "/admin/tool"
    assert route_family("https://example.com/") == "/"


def test_build_crawl_timing_summary_aggregates_page_and_run_stages() -> None:
    summary = build_crawl_timing_summary(
        run_dir="discovery-runs/test",
        page_timings=[
            PageTimingRecord(
                page_id="0001-my",
                normalized_url="https://example.com/my",
                page_type="dashboard",
                route_family="/my",
                total_duration_seconds=1.0,
                navigation_duration_seconds=0.4,
                settle_duration_seconds=0.3,
                extraction_duration_seconds=0.2,
                write_duration_seconds=0.1,
            ),
            PageTimingRecord(
                page_id="0002-admin",
                normalized_url="https://example.com/admin/tool/uploaduser/index.php",
                page_type="admin_tool_page",
                route_family="/admin/tool",
                total_duration_seconds=2.0,
                navigation_duration_seconds=0.8,
                settle_duration_seconds=0.5,
                extraction_duration_seconds=0.5,
                write_duration_seconds=0.2,
            ),
        ],
        total_run_duration_seconds=4.5,
        crawl_loop_duration_seconds=3.2,
        workflow_derivation_duration_seconds=0.4,
        manifest_write_duration_seconds=0.1,
        workflow_write_duration_seconds=0.2,
        timing_summary_generation_duration_seconds=0.05,
    )

    assert summary.page_count == 2
    assert summary.average_page_duration_seconds == 1.5
    assert summary.median_page_duration_seconds == 1.5
    assert summary.page_stage_totals["navigation_duration_seconds"] == 1.2
    assert summary.run_stage_totals["workflow_derivation_duration_seconds"] == 0.4
    assert summary.slowest_pages[0]["page_id"] == "0002-admin"
    assert summary.slowest_extraction_pages[0]["page_id"] == "0002-admin"
    assert summary.slowest_route_families[0]["route_family"] == "/admin/tool"
