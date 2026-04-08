from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

from moodle_sitemap.config import load_smoke_config
from moodle_sitemap.crawl import CrawlConfig, ProgressCallback, crawl_site
from moodle_sitemap.models import DiscoverySummary, PageRecord, SiteManifest


@dataclass(slots=True)
class DiscoveryRunResult:
    run_dir: Path
    manifest: SiteManifest
    summary: DiscoverySummary
    summary_path: Path
    report_path: Path


def create_discovery_run_dir(base_dir: str | Path = "discovery-runs") -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    run_dir = Path(base_dir) / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def run_discovery(
    *,
    config_path: str | Path,
    max_pages: int = 200,
    max_depth: int | None = 4,
    base_dir: str | Path = "discovery-runs",
    baseline_manifest_path: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> DiscoveryRunResult:
    config = load_smoke_config(config_path)
    run_dir = create_discovery_run_dir(base_dir)
    manifest = crawl_site(
        CrawlConfig(
            site_url=str(config.site_url),
            username=config.username,
            password=config.password,
            output_dir=run_dir,
            max_pages=max_pages,
            max_depth=max_depth,
            headless=config.headless,
            browser_engine=config.browser_engine,
        ),
        progress_callback=progress_callback,
    )

    baseline_manifest = load_optional_manifest(
        baseline_manifest_path or find_latest_manifest(Path("verification-runs"))
    )
    summary = build_discovery_summary(manifest, run_dir=run_dir, baseline_manifest=baseline_manifest)
    summary_path = run_dir / "discovery-summary.json"
    summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    report_path = run_dir / "discovery-summary.md"
    report_path.write_text(render_discovery_markdown(summary), encoding="utf-8")

    return DiscoveryRunResult(
        run_dir=run_dir,
        manifest=manifest,
        summary=summary,
        summary_path=summary_path,
        report_path=report_path,
    )


def build_discovery_summary(
    manifest: SiteManifest,
    *,
    run_dir: Path,
    baseline_manifest: SiteManifest | None = None,
) -> DiscoverySummary:
    pages = manifest.pages
    route_family_counts = Counter(route_family(page.normalized_url) for page in pages)
    query_heavy_counts = Counter(
        route_signature(page.normalized_url)
        for page in pages
        if urlparse(page.normalized_url).query
    )
    canonicalization_events = sum(
        1
        for page in pages
        if page.url != page.normalized_url or page.final_url != page.normalized_url
    )
    slowest_pages = sorted(
        (
            {
                "page_id": page.page_id,
                "normalized_url": page.normalized_url,
                "page_type": page.page_type.value,
                "load_duration_seconds": page.load_duration_seconds or 0.0,
            }
            for page in pages
            if page.load_duration_seconds is not None
        ),
        key=lambda item: item["load_duration_seconds"],
        reverse=True,
    )[:5]
    unknown_pages_detail = [
        {
            "page_id": page.page_id,
            "normalized_url": page.normalized_url,
            "title": page.title or "",
        }
        for page in pages
        if page.page_type.value == "unknown"
    ]
    weak_candidates = [
        {
            "page_id": page.page_id,
            "normalized_url": page.normalized_url,
            "page_type": page.page_type.value,
        }
        for page in pages
        if page.page_type.value in {"unknown", "admin_settings"}
    ][:10]
    exclusion_candidates = [
        {"route_family": family, "count": count}
        for family, count in route_family_counts.items()
        if "calendar/" in family or "switchrole" in family
    ]

    baseline_families = (
        {route_family(page.normalized_url) for page in baseline_manifest.pages}
        if baseline_manifest
        else set()
    )
    newly_seen_route_families = sorted(
        family for family in route_family_counts if family not in baseline_families
    )

    return DiscoverySummary(
        site_url=manifest.site_url,
        run_dir=str(run_dir),
        total_pages=manifest.visited_pages,
        unique_normalized_urls=len({page.normalized_url for page in pages}),
        unknown_pages=manifest.summary.unknown_pages,
        crawl_duration_seconds=(
            manifest.crawl_finished_at - manifest.crawl_started_at
        ).total_seconds(),
        max_depth_reached=max((page.crawl_depth for page in pages), default=0),
        page_type_counts=manifest.summary.page_type_counts,
        top_route_families=[
            {"route_family": family, "count": count}
            for family, count in route_family_counts.most_common(10)
        ],
        query_heavy_routes=[
            {"route_signature": signature, "count": count}
            for signature, count in query_heavy_counts.most_common(10)
        ],
        canonicalization_events=canonicalization_events,
        slowest_pages=slowest_pages,
        unknown_pages_detail=unknown_pages_detail,
        weak_classification_candidates=weak_candidates,
        exclusion_candidates=exclusion_candidates,
        newly_seen_route_families=newly_seen_route_families,
    )


def route_family(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if not parts:
        return "/"
    return "/" + "/".join(parts[:2])


def route_signature(url: str) -> str:
    parsed = urlparse(url)
    query_keys = sorted(key for key, _ in parse_qsl(parsed.query, keep_blank_values=True))
    if not query_keys:
        return parsed.path or "/"
    return f"{parsed.path}?{','.join(query_keys)}"


def find_latest_manifest(base_dir: Path) -> Path | None:
    if not base_dir.exists():
        return None
    candidates = sorted(
        (path / "sitemap.json" for path in base_dir.iterdir() if path.is_dir()),
        reverse=True,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_optional_manifest(path: str | Path | None) -> SiteManifest | None:
    if path is None:
        return None
    manifest_path = Path(path)
    if not manifest_path.exists():
        return None
    return SiteManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def render_discovery_markdown(summary: DiscoverySummary) -> str:
    lines = [
        "# Discovery Summary",
        "",
        f"- Site URL: `{summary.site_url}`",
        f"- Run directory: `{summary.run_dir}`",
        f"- Total pages: `{summary.total_pages}`",
        f"- Unique normalized URLs: `{summary.unique_normalized_urls}`",
        f"- Unknown pages: `{summary.unknown_pages}`",
        f"- Crawl duration (seconds): `{summary.crawl_duration_seconds}`",
        f"- Max depth reached: `{summary.max_depth_reached}`",
        "",
        "## Top Route Families",
    ]
    for item in summary.top_route_families:
        lines.append(f"- `{item['route_family']}`: {item['count']}")
    lines.extend(["", "## Newly Seen Route Families"])
    for family in summary.newly_seen_route_families:
        lines.append(f"- `{family}`")
    lines.extend(["", "## Unknown Pages"])
    if summary.unknown_pages_detail:
        for item in summary.unknown_pages_detail:
            lines.append(f"- `{item['normalized_url']}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Recommended Next Review Areas"])
    recommendations = recommended_next_actions(summary)
    for item in recommendations:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def recommended_next_actions(summary: DiscoverySummary) -> list[str]:
    actions: list[str] = []
    if summary.unknown_pages_detail:
        actions.append("Review the remaining unknown pages for route-specific classifier additions.")
    if summary.query_heavy_routes:
        actions.append("Inspect query-heavy route patterns for possible low-value variants or future exclusions.")
    if summary.canonicalization_events:
        actions.append("Review canonicalization events to confirm redirected URLs are still collapsing as intended.")
    if summary.slowest_pages:
        actions.append("Inspect the slowest pages and route families for expensive admin or calendar surfaces.")
    if summary.exclusion_candidates:
        actions.append("Consider whether repeated utility pages should eventually be excluded from large discovery runs.")
    return actions[:5]
