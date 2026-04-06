from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from moodle_sitemap.auth import login_to_moodle
from moodle_sitemap.browser import open_browser
from moodle_sitemap.classify import classify_page
from moodle_sitemap.discover import (
    canonicalize_resolved_url,
    filter_discovered_links,
    make_page_id,
    normalize_url,
    same_origin,
)
from moodle_sitemap.extract.dom import extract_anchor_hrefs, extract_page_features
from moodle_sitemap.extract.footer import extract_footer_info
from moodle_sitemap.extract.network import NetworkRecorder
from moodle_sitemap.models import BrowserEngine, PageRecord, SiteManifest
from moodle_sitemap.storage.json_store import JsonStore


@dataclass(slots=True)
class CrawlConfig:
    site_url: str
    username: str
    password: str
    output_dir: Path
    max_pages: int = 200
    headless: bool = True
    browser_engine: BrowserEngine = BrowserEngine.CHROMIUM


@dataclass
class CrawlVisitIndex:
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


def crawl_site(config: CrawlConfig) -> SiteManifest:
    start_url = normalize_url(config.site_url)
    parsed_site = urlparse(start_url)
    origin = f"{parsed_site.scheme}://{parsed_site.netloc}"

    store = JsonStore(config.output_dir)
    store.prepare()

    visit_index = CrawlVisitIndex()
    queue: deque[tuple[str, str | None]] = deque([(start_url, None)])
    visit_index.mark_queued(start_url)
    page_records: list[PageRecord] = []

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
            while queue and len(page_records) < config.max_pages:
                target_url, referrer = queue.popleft()
                visit_index.mark_dequeued(target_url)
                if visit_index.should_skip_target(target_url):
                    continue

                recorder.reset()
                response = session.page.goto(target_url, wait_until="domcontentloaded")
                try:
                    session.page.wait_for_load_state("networkidle", timeout=5_000)
                except PlaywrightTimeoutError:
                    pass

                final_url = normalize_url(session.page.url)
                if not same_origin(final_url, origin):
                    visit_index.visited_targets.add(target_url)
                    continue
                normalized_url = canonicalize_resolved_url(target_url, final_url)

                if not visit_index.mark_visited(target_url, normalized_url):
                    continue

                features = extract_page_features(session.page)
                discovered_links = filter_discovered_links(
                    extract_anchor_hrefs(session.page),
                    base_url=normalized_url,
                    origin=origin,
                )

                page_record = PageRecord(
                    page_id=make_page_id(len(page_records) + 1, normalized_url),
                    url=target_url,
                    normalized_url=normalized_url,
                    final_url=final_url,
                    title=session.page.title(),
                    page_type=classify_page(normalized_url, features),
                    referrer=referrer,
                    http_status=response.status if response else None,
                    features=features,
                    footer=extract_footer_info(session.page),
                    discovered_links=discovered_links,
                    network=list(recorder.events),
                )
                store.write_page(page_record)
                page_records.append(page_record)

                for link in discovered_links:
                    if len(visit_index.visited_normalized) + len(queue) >= config.max_pages:
                        break
                    if not visit_index.mark_queued(link):
                        continue
                    queue.append((link, final_url))
        finally:
            recorder.detach()

    manifest = SiteManifest(
        site_url=start_url,
        origin=origin,
        max_pages=config.max_pages,
        visited_pages=len(page_records),
        pages=page_records,
    )
    store.write_manifest(manifest)
    return manifest
