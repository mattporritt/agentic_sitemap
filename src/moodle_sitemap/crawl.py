from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from moodle_sitemap.auth import login_to_moodle
from moodle_sitemap.browser import open_browser
from moodle_sitemap.classify import classify_page
from moodle_sitemap.discover import filter_discovered_links, make_page_id, normalize_url, same_origin
from moodle_sitemap.extract.dom import extract_anchor_hrefs, extract_page_features
from moodle_sitemap.extract.footer import extract_footer_info
from moodle_sitemap.extract.network import NetworkRecorder
from moodle_sitemap.models import PageRecord, SiteManifest
from moodle_sitemap.storage.json_store import JsonStore


@dataclass(slots=True)
class CrawlConfig:
    site_url: str
    username: str
    password: str
    output_dir: Path
    max_pages: int = 200
    headless: bool = True


def crawl_site(config: CrawlConfig) -> SiteManifest:
    start_url = normalize_url(config.site_url)
    parsed_site = urlparse(start_url)
    origin = f"{parsed_site.scheme}://{parsed_site.netloc}"

    store = JsonStore(config.output_dir)
    store.prepare()

    visited: set[str] = set()
    queued: set[str] = {start_url}
    queue: deque[tuple[str, str | None]] = deque([(start_url, None)])
    page_records: list[PageRecord] = []

    with open_browser(headless=config.headless) as session:
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
                queued.discard(target_url)
                if target_url in visited:
                    continue

                recorder.reset()
                response = session.page.goto(target_url, wait_until="domcontentloaded")
                try:
                    session.page.wait_for_load_state("networkidle", timeout=5_000)
                except PlaywrightTimeoutError:
                    pass

                final_url = normalize_url(session.page.url)
                if not same_origin(final_url, origin):
                    visited.add(target_url)
                    continue

                features = extract_page_features(session.page)
                discovered_links = filter_discovered_links(
                    extract_anchor_hrefs(session.page),
                    base_url=final_url,
                    origin=origin,
                )

                page_record = PageRecord(
                    page_id=make_page_id(len(page_records) + 1, final_url),
                    url=target_url,
                    final_url=final_url,
                    title=session.page.title(),
                    page_type=classify_page(final_url, features),
                    referrer=referrer,
                    http_status=response.status if response else None,
                    features=features,
                    footer=extract_footer_info(session.page),
                    discovered_links=discovered_links,
                    network=list(recorder.events),
                )
                store.write_page(page_record)
                page_records.append(page_record)
                visited.add(target_url)

                for link in discovered_links:
                    if link in visited or link in queued:
                        continue
                    if len(visited) + len(queue) >= config.max_pages:
                        break
                    queue.append((link, final_url))
                    queued.add(link)
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
