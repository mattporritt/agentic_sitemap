from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from moodle_sitemap.config import load_smoke_config
from moodle_sitemap.crawl import CrawlConfig, ProgressCallback, crawl_site
from moodle_sitemap.smoke import SmokeRunResult, run_smoke_test


@dataclass(slots=True)
class VerificationRunResult:
    run_dir: Path
    smoke: SmokeRunResult
    visited_pages: int


def create_verification_run_dir(base_dir: str | Path = "verification-runs") -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    run_dir = Path(base_dir) / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def run_verification(
    *,
    config_path: str | Path,
    max_pages: int,
    base_dir: str | Path = "verification-runs",
    progress_callback: ProgressCallback | None = None,
) -> VerificationRunResult:
    config = load_smoke_config(config_path)
    run_dir = create_verification_run_dir(base_dir)
    smoke = run_smoke_test(config_path=config_path, output_dir=run_dir)
    manifest = crawl_site(
        CrawlConfig(
            site_url=str(config.site_url),
            username=config.username,
            password=config.password,
            output_dir=run_dir,
            max_pages=max_pages,
            headless=config.headless,
            browser_engine=config.browser_engine,
        ),
        progress_callback=progress_callback,
    )
    return VerificationRunResult(run_dir=run_dir, smoke=smoke, visited_pages=manifest.visited_pages)
