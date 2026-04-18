# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

"""Core crawl orchestration for authenticated Moodle site mapping.

This module owns the main browser-backed crawl loop. It is responsible for
turning visited pages into stable `PageRecord` artifacts and then deriving the
manifest and workflow graph from those page records.
"""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from moodle_sitemap.auth import login_to_moodle
from moodle_sitemap.browser import open_browser
from moodle_sitemap.classify import classify_page
from moodle_sitemap.discover import (
    canonicalize_resolved_url,
    filter_discovered_links,
    make_page_id,
    normalize_url,
    prioritize_discovered_links,
    same_origin,
)
from moodle_sitemap.extract.dom import extract_anchor_hrefs, extract_page_features, refine_task_summary_for_page_type
from moodle_sitemap.extract.footer import extract_footer_info
from moodle_sitemap.extract.network import NetworkRecorder
from moodle_sitemap.models import (
    BrowserEngine,
    ManifestSummary,
    PageRecord,
    PageTimingRecord,
    PageType,
    SettleStrategy,
    SiteManifest,
)
from moodle_sitemap.safety import summarize_page_safety
from moodle_sitemap.settle import apply_settle_strategy
from moodle_sitemap.storage.json_store import JsonStore
from moodle_sitemap.timing import build_crawl_timing_summary, route_family
from moodle_sitemap.workflow import derive_workflow_graph


@dataclass(slots=True)
class CrawlConfig:
    """Runtime options for a single crawl execution."""

    site_url: str
    username: str
    password: str
    output_dir: Path
    role_profile: str = "unlabeled"
    max_pages: int = 200
    max_depth: int | None = None
    headless: bool = True
    browser_engine: BrowserEngine = BrowserEngine.CHROMIUM
    settle_strategy: SettleStrategy = SettleStrategy.NETWORKIDLE


ProgressCallback = Callable[[PageRecord, int, int], None]


@dataclass
class CrawlVisitIndex:
    """Tracks queued, visited, and aliased URLs during a crawl.

    Moodle often exposes the same destination through several safe variants.
    This index keeps de-duplication conservative by remembering both requested
    targets and their resolved normalized destinations.
    """

    visited_targets: set[str] = field(default_factory=set)
    visited_normalized: set[str] = field(default_factory=set)
    queued_targets: set[str] = field(default_factory=set)
    aliases: dict[str, str] = field(default_factory=dict)

    def should_skip_target(self, target_url: str) -> bool:
        return (
            target_url in self.visited_targets
            or target_url in self.visited_normalized
            or target_url in self.aliases
        )

    def mark_queued(self, target_url: str) -> bool:
        if self.should_skip_target(target_url) or target_url in self.queued_targets:
            return False
        self.queued_targets.add(target_url)
        return True

    def mark_dequeued(self, target_url: str) -> None:
        self.queued_targets.discard(target_url)

    def mark_visited(self, target_url: str, normalized_url: str) -> bool:
        self.visited_targets.add(target_url)
        self.aliases[target_url] = normalized_url
        self.aliases[normalized_url] = normalized_url
        if normalized_url in self.visited_normalized:
            return False
        self.visited_normalized.add(normalized_url)
        return True


def crawl_site(
    config: CrawlConfig,
    *,
    progress_callback: ProgressCallback | None = None,
) -> SiteManifest:
    """Run a bounded authenticated crawl and write its JSON artifacts.

    The crawl is intentionally conservative: same-origin only, safe links only,
    and no form submission. Classification, task-summary refinement, safety
    summarization, and workflow derivation all happen from the visited pages in
    this function so the saved artifacts stay internally consistent.
    """

    crawl_started_at = datetime.now(timezone.utc)
    run_started = perf_counter()
    start_url = normalize_url(config.site_url)
    parsed_site = urlparse(start_url)
    origin = f"{parsed_site.scheme}://{parsed_site.netloc}"

    store = JsonStore(config.output_dir)
    store.prepare()

    visit_index = CrawlVisitIndex()
    queue: deque[tuple[str, str | None, int]] = deque([(start_url, None, 0)])
    visit_index.mark_queued(start_url)
    page_records: list[PageRecord] = []
    page_timings: list[PageTimingRecord] = []

    with open_browser(headless=config.headless, engine=config.browser_engine) as session:
        login_to_moodle(
            page=session.page,
            site_url=start_url,
            username=config.username,
            password=config.password,
        )
        recorder = NetworkRecorder(session.page)
        recorder.attach()

        try:
            crawl_loop_started = perf_counter()
            while queue and len(page_records) < config.max_pages:
                target_url, referrer, depth = queue.popleft()
                visit_index.mark_dequeued(target_url)
                if visit_index.should_skip_target(target_url):
                    continue

                page_started = perf_counter()
                recorder.reset()
                navigation_started = perf_counter()
                try:
                    response = session.page.goto(target_url, wait_until="domcontentloaded")
                except (PlaywrightError, PlaywrightTimeoutError) as error:
                    if is_download_navigation_error(error):
                        visit_index.visited_targets.add(target_url)
                        continue
                    if is_navigation_timeout_error(error):
                        visit_index.visited_targets.add(target_url)
                        continue
                    raise
                navigation_duration_seconds = perf_counter() - navigation_started
                settle_started = perf_counter()
                apply_settle_strategy(session.page, config.settle_strategy)
                settle_duration_seconds = perf_counter() - settle_started
                load_duration_seconds = navigation_duration_seconds + settle_duration_seconds

                final_url = normalize_url(session.page.url)
                if not same_origin(final_url, origin):
                    visit_index.visited_targets.add(target_url)
                    continue
                normalized_url = canonicalize_resolved_url(target_url, final_url)

                if not visit_index.mark_visited(target_url, normalized_url):
                    continue

                extraction_started = perf_counter()
                features = extract_page_features(session.page)
                discovered_links = filter_discovered_links(
                    extract_anchor_hrefs(session.page),
                    base_url=normalized_url,
                    origin=origin,
                )

                page_type = classify_page(normalized_url, features)
                refined_task_summary = refine_task_summary_for_page_type(page_type, features.task_summary)
                page_record = PageRecord(
                    page_id=make_page_id(len(page_records) + 1, normalized_url),
                    url=target_url,
                    normalized_url=normalized_url,
                    final_url=final_url,
                    title=session.page.title(),
                    page_type=page_type,
                    referrer=referrer,
                    http_status=response.status if response else None,
                    body_id=features.body_id,
                    body_classes=features.body_classes,
                    breadcrumbs=features.breadcrumbs,
                    affordances=features.affordances,
                    task_summary=refined_task_summary,
                    primary_page_intent=refined_task_summary.primary_page_intent,
                    primary_actions=refined_task_summary.primary_actions,
                    task_relevance_score=refined_task_summary.task_relevance_score,
                    safety=summarize_page_safety(features.affordances),
                    footer=extract_footer_info(session.page),
                    discovered_links=discovered_links,
                    network=list(recorder.events),
                    crawl_depth=depth,
                    load_duration_seconds=round(load_duration_seconds, 6),
                )
                extraction_duration_seconds = perf_counter() - extraction_started
                write_started = perf_counter()
                store.write_page(page_record)
                write_duration_seconds = perf_counter() - write_started
                page_records.append(page_record)
                page_timings.append(
                    PageTimingRecord(
                        page_id=page_record.page_id,
                        normalized_url=page_record.normalized_url,
                        page_type=page_record.page_type.value,
                        route_family=route_family(page_record.normalized_url),
                        crawl_depth=depth,
                        total_duration_seconds=round(perf_counter() - page_started, 6),
                        navigation_duration_seconds=round(navigation_duration_seconds, 6),
                        settle_duration_seconds=round(settle_duration_seconds, 6),
                        extraction_duration_seconds=round(extraction_duration_seconds, 6),
                        write_duration_seconds=round(write_duration_seconds, 6),
                    )
                )
                if progress_callback:
                    progress_callback(page_record, len(page_records), config.max_pages)

                if config.max_depth is not None and depth >= config.max_depth:
                    continue

                for link in prioritize_discovered_links(discovered_links):
                    if len(visit_index.visited_normalized) + len(queue) >= config.max_pages:
                        break
                    if not visit_index.mark_queued(link):
                        continue
                    queue.append((link, final_url, depth + 1))
        finally:
            recorder.detach()
        crawl_loop_duration_seconds = perf_counter() - crawl_loop_started

    crawl_finished_at = datetime.now(timezone.utc)
    workflow_started = perf_counter()
    workflow_graph = derive_workflow_graph(page_records, role_profile=config.role_profile)
    workflow_derivation_duration_seconds = perf_counter() - workflow_started
    for page_record in page_records:
        store.write_page(page_record)
    manifest = SiteManifest(
        site_url=start_url,
        role_profile=config.role_profile,
        settle_strategy=config.settle_strategy,
        origin=origin,
        crawl_started_at=crawl_started_at,
        crawl_finished_at=crawl_finished_at,
        max_pages=config.max_pages,
        visited_pages=len(page_records),
        summary=build_manifest_summary(
            page_records,
            workflow_edge_count=workflow_graph.total_edges,
            crawl_started_at=crawl_started_at,
            crawl_finished_at=crawl_finished_at,
        ),
        pages=page_records,
    )
    manifest_write_started = perf_counter()
    store.write_manifest(manifest)
    manifest_write_duration_seconds = perf_counter() - manifest_write_started
    workflow_write_started = perf_counter()
    store.write_workflow_graph(workflow_graph)
    workflow_write_duration_seconds = perf_counter() - workflow_write_started
    timing_summary_started = perf_counter()
    timing_summary = build_crawl_timing_summary(
        run_dir=config.output_dir,
        settle_strategy=config.settle_strategy,
        page_timings=page_timings,
        total_run_duration_seconds=perf_counter() - run_started,
        crawl_loop_duration_seconds=crawl_loop_duration_seconds,
        workflow_derivation_duration_seconds=workflow_derivation_duration_seconds,
        manifest_write_duration_seconds=manifest_write_duration_seconds,
        workflow_write_duration_seconds=workflow_write_duration_seconds,
    )
    page_timings_write_started = perf_counter()
    store.write_page_timings(page_timings)
    page_timings_write_duration_seconds = perf_counter() - page_timings_write_started
    timing_summary = timing_summary.model_copy(
        update={
            "run_stage_totals": {
                **timing_summary.run_stage_totals,
                "page_timings_write_duration_seconds": round(
                    page_timings_write_duration_seconds, 6
                ),
                "timing_summary_generation_duration_seconds": round(
                    perf_counter() - timing_summary_started, 6
                ),
            }
        }
    )
    timing_summary_write_started = perf_counter()
    store.write_timing_summary(timing_summary)
    timing_summary_write_duration_seconds = perf_counter() - timing_summary_write_started
    timing_summary = timing_summary.model_copy(
        update={
            "total_run_duration_seconds": round(perf_counter() - run_started, 6),
            "run_stage_totals": {
                **timing_summary.run_stage_totals,
                "timing_summary_write_duration_seconds": round(
                    timing_summary_write_duration_seconds, 6
                ),
            },
        }
    )
    store.write_timing_summary(timing_summary)
    return manifest


def format_progress_line(page: PageRecord, *, current_count: int, max_pages: int) -> str:
    """Render a short CLI progress line for a visited page."""

    return (
        f"[{current_count}/{max_pages}] "
        f"{page.page_id} "
        f"{page.page_type.value} "
        f"{page.normalized_url}"
    )


def is_download_navigation_error(error: Exception) -> bool:
    """Return true when Playwright rejected navigation because a download started."""

    return "download is starting" in str(error).lower()


def is_navigation_timeout_error(error: Exception) -> bool:
    """Return true when Playwright timed out before DOMContentLoaded."""

    return "page.goto" in str(error).lower() and "timeout" in str(error).lower()


def build_manifest_summary(
    pages: list[PageRecord],
    *,
    workflow_edge_count: int = 0,
    crawl_started_at: datetime,
    crawl_finished_at: datetime,
) -> ManifestSummary:
    page_type_counts = {page_type.value: 0 for page_type in PageType}
    for page in pages:
        page_type_counts[page.page_type.value] += 1

    return ManifestSummary(
        total_pages=len(pages),
        unknown_pages=page_type_counts[PageType.UNKNOWN.value],
        workflow_edge_count=workflow_edge_count,
        page_type_counts=page_type_counts,
        crawl_started_at=crawl_started_at,
        crawl_finished_at=crawl_finished_at,
    )
