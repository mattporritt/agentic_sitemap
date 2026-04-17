# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from moodle_sitemap.models import (
    DiscoverySummary,
    LikelyIntent,
    ManifestSummary,
    PageRecord,
    PageType,
    SettleComparisonRun,
    SettleStrategy,
    SiteManifest,
)
from moodle_sitemap.settle_compare import (
    build_crawl_surface_delta,
    build_settle_comparison_summary,
    build_strategy_delta,
    render_settle_comparison_markdown,
)


def make_page(page_id: str, url: str, *, page_type: PageType, with_next_steps: bool = False) -> PageRecord:
    return PageRecord(
        page_id=page_id,
        url=url,
        normalized_url=url,
        final_url=url,
        title=page_id,
        page_type=page_type,
        body_classes=[],
        breadcrumbs=[],
        primary_page_intent=LikelyIntent.NAVIGATE,
        next_steps=(
            [
                {
                    "target_url": "https://example.com/course/view.php?id=4",
                    "target_page_type": "course_view",
                }
            ]
            if with_next_steps
            else []
        ),
        discovered_links=[],
        network=[],
    )


def make_manifest(
    pages: list[PageRecord],
    *,
    settle_strategy: SettleStrategy,
) -> SiteManifest:
    started = datetime(2026, 4, 17, 0, 0, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 4, 17, 0, 1, 0, tzinfo=timezone.utc)
    return SiteManifest(
        site_url="https://example.com",
        role_profile="admin",
        settle_strategy=settle_strategy,
        origin="https://example.com",
        crawl_started_at=started,
        crawl_finished_at=ended,
        max_pages=20,
        visited_pages=len(pages),
        summary=ManifestSummary(
            total_pages=len(pages),
            unknown_pages=sum(1 for page in pages if page.page_type == PageType.UNKNOWN),
            workflow_edge_count=5,
            page_type_counts={page_type.value: sum(1 for page in pages if page.page_type == page_type) for page_type in PageType},
            crawl_started_at=started,
            crawl_finished_at=ended,
        ),
        pages=pages,
    )


class StubDiscoveryRunResult:
    def __init__(self, run_dir: Path, manifest: SiteManifest, summary: DiscoverySummary) -> None:
        self.run_dir = run_dir
        self.manifest = manifest
        self.summary = summary
        self.summary_path = run_dir / "discovery-summary.json"
        self.report_path = run_dir / "discovery-summary.md"


def make_discovery_result(
    tmp_path: Path,
    *,
    strategy: SettleStrategy,
    crawl_duration_seconds: float,
    settle_duration_seconds: float,
    total_pages: int,
    unknown_pages: int,
    workflow_edge_count: int,
    next_step_pages: int,
) -> StubDiscoveryRunResult:
    pages = [
        make_page(
            f"{index:04d}-page",
            f"https://example.com/page{index}.php",
            page_type=PageType.DASHBOARD if index == 1 else PageType.COURSE_VIEW,
            with_next_steps=index <= next_step_pages,
        )
        for index in range(1, total_pages + 1)
    ]
    for index in range(unknown_pages):
        pages[index].page_type = PageType.UNKNOWN
    manifest = make_manifest(pages, settle_strategy=strategy)
    run_dir = tmp_path / strategy.value
    run_dir.mkdir()
    summary = DiscoverySummary(
        site_url="https://example.com",
        role_profile="admin",
        run_dir=str(run_dir),
        settle_strategy=strategy,
        total_pages=total_pages,
        unique_normalized_urls=total_pages,
        unknown_pages=unknown_pages,
        workflow_edge_count=workflow_edge_count,
        crawl_duration_seconds=crawl_duration_seconds,
        average_page_duration_seconds=round(crawl_duration_seconds / max(total_pages, 1), 6),
        median_page_duration_seconds=round(crawl_duration_seconds / max(total_pages, 1), 6),
        page_stage_totals={
            "navigation_duration_seconds": 10.0,
            "settle_duration_seconds": settle_duration_seconds,
            "extraction_duration_seconds": 1.0,
            "write_duration_seconds": 0.1,
        },
        run_stage_totals={},
        max_depth_reached=3,
        page_type_counts=manifest.summary.page_type_counts,
        workflow_edge_weight_counts={"high": workflow_edge_count},
        workflow_edge_relevance_counts={"task": workflow_edge_count},
        intent_populated_pages=total_pages,
    )
    return StubDiscoveryRunResult(run_dir, manifest, summary)


def test_build_strategy_delta_reports_timing_and_quality_deltas() -> None:
    baseline = SettleComparisonRun(
        settle_strategy=SettleStrategy.NETWORKIDLE,
        run_dir="baseline",
        total_pages=10,
        unknown_pages=1,
        workflow_edge_count=5,
        next_step_page_count=6,
        intent_populated_pages=10,
        crawl_duration_seconds=20.0,
        average_page_duration_seconds=2.0,
        median_page_duration_seconds=2.0,
        navigation_duration_seconds=12.0,
        settle_duration_seconds=6.0,
        extraction_duration_seconds=1.0,
        write_duration_seconds=0.1,
        page_type_counts={"dashboard": 1, "course_view": 9},
    )
    candidate = baseline.model_copy(
        update={
            "settle_strategy": SettleStrategy.ADAPTIVE,
            "crawl_duration_seconds": 17.0,
            "settle_duration_seconds": 3.0,
            "workflow_edge_count": 4,
            "next_step_page_count": 5,
        }
    )

    delta = build_strategy_delta(baseline, candidate)

    assert delta["strategy"] == "adaptive"
    assert delta["crawl_duration_delta_seconds"] == -3.0
    assert delta["settle_duration_delta_seconds"] == -3.0
    assert delta["workflow_edge_delta"] == -1
    assert delta["next_step_page_delta"] == -1


def test_build_settle_comparison_summary_prefers_fast_non_regressing_strategy(tmp_path: Path) -> None:
    baseline = make_discovery_result(
        tmp_path,
        strategy=SettleStrategy.NETWORKIDLE,
        crawl_duration_seconds=20.0,
        settle_duration_seconds=6.0,
        total_pages=10,
        unknown_pages=1,
        workflow_edge_count=5,
        next_step_pages=6,
    )
    short_settle = make_discovery_result(
        tmp_path,
        strategy=SettleStrategy.DOMCONTENTLOADED_SHORT_SETTLE,
        crawl_duration_seconds=16.0,
        settle_duration_seconds=2.5,
        total_pages=10,
        unknown_pages=1,
        workflow_edge_count=5,
        next_step_pages=6,
    )
    fast_but_weaker = make_discovery_result(
        tmp_path,
        strategy=SettleStrategy.DOMCONTENTLOADED,
        crawl_duration_seconds=14.0,
        settle_duration_seconds=0.0,
        total_pages=9,
        unknown_pages=2,
        workflow_edge_count=3,
        next_step_pages=4,
    )

    summary = build_settle_comparison_summary(
        config_path="config.toml",
        max_pages=40,
        max_depth=4,
        run_results=[baseline, short_settle, fast_but_weaker],
    )

    assert summary.baseline_strategy == SettleStrategy.NETWORKIDLE
    assert summary.fastest_strategy == SettleStrategy.DOMCONTENTLOADED
    assert summary.recommended_strategy == SettleStrategy.DOMCONTENTLOADED_SHORT_SETTLE
    assert summary.strategy_deltas[0]["strategy"] == "domcontentloaded_short_settle"
    assert summary.crawl_surface_deltas[0]["strategy"] == "domcontentloaded_short_settle"
    assert summary.quality_regressions[0]["strategy"] == "domcontentloaded"


def test_render_settle_comparison_markdown_includes_recommendation(tmp_path: Path) -> None:
    summary = build_settle_comparison_summary(
        config_path="config.toml",
        max_pages=40,
        max_depth=4,
        run_results=[
            make_discovery_result(
                tmp_path,
                strategy=SettleStrategy.NETWORKIDLE,
                crawl_duration_seconds=20.0,
                settle_duration_seconds=6.0,
                total_pages=10,
                unknown_pages=1,
                workflow_edge_count=5,
                next_step_pages=6,
            ),
            make_discovery_result(
                tmp_path,
                strategy=SettleStrategy.ADAPTIVE,
                crawl_duration_seconds=17.0,
                settle_duration_seconds=3.0,
                total_pages=10,
                unknown_pages=1,
                workflow_edge_count=5,
                next_step_pages=6,
            ),
        ],
    )

    markdown = render_settle_comparison_markdown(summary)

    assert "# Settle Comparison" in markdown
    assert "Recommended strategy" in markdown
    assert "Crawl surface overlap" in markdown


def test_build_crawl_surface_delta_reports_page_and_route_overlap(tmp_path: Path) -> None:
    baseline = make_discovery_result(
        tmp_path,
        strategy=SettleStrategy.NETWORKIDLE,
        crawl_duration_seconds=20.0,
        settle_duration_seconds=6.0,
        total_pages=3,
        unknown_pages=0,
        workflow_edge_count=5,
        next_step_pages=2,
    )
    baseline.manifest.pages[0].normalized_url = "https://example.com/my"
    baseline.manifest.pages[1].normalized_url = "https://example.com/course/view.php?id=4"
    baseline.manifest.pages[2].normalized_url = "https://example.com/admin/search.php"

    candidate = make_discovery_result(
        tmp_path,
        strategy=SettleStrategy.ADAPTIVE,
        crawl_duration_seconds=17.0,
        settle_duration_seconds=3.0,
        total_pages=3,
        unknown_pages=0,
        workflow_edge_count=5,
        next_step_pages=2,
    )
    candidate.manifest.pages[0].normalized_url = "https://example.com/my"
    candidate.manifest.pages[1].normalized_url = "https://example.com/admin/search.php"
    candidate.manifest.pages[2].normalized_url = "https://example.com/admin/tool/uploaduser/index.php"

    delta = build_crawl_surface_delta(baseline, candidate)

    assert delta["strategy"] == "adaptive"
    assert delta["shared_normalized_url_count"] == 2
    assert delta["baseline_only_page_count"] == 1
    assert delta["candidate_only_page_count"] == 1
    assert "/course/view.php" in delta["baseline_only_route_families"]
    assert "/admin/tool" in delta["candidate_only_route_families"]
