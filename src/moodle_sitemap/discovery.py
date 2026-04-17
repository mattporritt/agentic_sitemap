# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

"""Discovery-run orchestration and post-run summary generation.

Discovery mode builds on the normal crawl output. Its job is to widen the crawl
budget and then summarize what that broader run surfaced in a way that is easy
for humans and downstream tooling to inspect.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from urllib.parse import parse_qsl, urlparse

from moodle_sitemap.config import load_smoke_config
from moodle_sitemap.crawl import CrawlConfig, ProgressCallback, crawl_site
from moodle_sitemap.models import (
    CrawlTimingSummary,
    DiscoverySummary,
    PageRecord,
    SettleStrategy,
    SiteManifest,
    WorkflowFamilySummary,
)


@dataclass(slots=True)
class DiscoveryRunResult:
    """Paths and parsed models produced by a single discovery run."""

    run_dir: Path
    manifest: SiteManifest
    summary: DiscoverySummary
    summary_path: Path
    report_path: Path


def create_discovery_run_dir(base_dir: str | Path = "discovery-runs") -> Path:
    """Create a timestamped directory for one discovery run."""

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    run_dir = Path(base_dir) / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def run_discovery(
    *,
    config_path: str | Path,
    max_pages: int = 200,
    max_depth: int | None = 4,
    settle_strategy: SettleStrategy | None = None,
    base_dir: str | Path = "discovery-runs",
    baseline_manifest_path: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> DiscoveryRunResult:
    """Run a broader bounded crawl and write discovery summary artifacts."""

    config = load_smoke_config(config_path)
    selected_settle_strategy = settle_strategy or SettleStrategy.ADAPTIVE
    run_dir = create_discovery_run_dir(base_dir)
    manifest = crawl_site(
        CrawlConfig(
            site_url=str(config.site_url),
            username=config.username,
            password=config.password,
            output_dir=run_dir,
            role_profile=config.role_profile,
            max_pages=max_pages,
            max_depth=max_depth,
            headless=config.headless,
            browser_engine=config.browser_engine,
            settle_strategy=selected_settle_strategy,
        ),
        progress_callback=progress_callback,
    )

    baseline_manifest = load_optional_manifest(
        baseline_manifest_path or find_latest_manifest(Path("verification-runs"))
    )
    discovery_summary_started = perf_counter()
    summary = build_discovery_summary(manifest, run_dir=run_dir, baseline_manifest=baseline_manifest)
    discovery_summary_generation_duration_seconds = perf_counter() - discovery_summary_started
    summary = summary.model_copy(
        update={
            "run_stage_totals": {
                **summary.run_stage_totals,
                "discovery_summary_generation_duration_seconds": round(
                    discovery_summary_generation_duration_seconds, 6
                ),
            }
        }
    )
    report_path = run_dir / "discovery-summary.md"
    summary_path = run_dir / "discovery-summary.json"
    summary_write_started = perf_counter()
    summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    discovery_summary_write_duration_seconds = perf_counter() - summary_write_started
    summary = summary.model_copy(
        update={
            "run_stage_totals": {
                **summary.run_stage_totals,
                "discovery_summary_write_duration_seconds": round(
                    discovery_summary_write_duration_seconds, 6
                ),
            }
        }
    )
    report_write_started = perf_counter()
    report_path.write_text(render_discovery_markdown(summary), encoding="utf-8")
    discovery_report_write_duration_seconds = perf_counter() - report_write_started
    summary = summary.model_copy(
        update={
            "run_stage_totals": {
                **summary.run_stage_totals,
                "discovery_report_write_duration_seconds": round(
                    discovery_report_write_duration_seconds, 6
                ),
            }
        }
    )
    summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    timing_summary = load_timing_summary(run_dir)
    if timing_summary is not None:
        updated_timing_summary = timing_summary.model_copy(
            update={
                "total_run_duration_seconds": round(
                    timing_summary.total_run_duration_seconds
                    + discovery_summary_generation_duration_seconds
                    + discovery_summary_write_duration_seconds
                    + discovery_report_write_duration_seconds,
                    6,
                ),
                "run_stage_totals": {
                    **timing_summary.run_stage_totals,
                    "discovery_summary_generation_duration_seconds": round(
                        discovery_summary_generation_duration_seconds, 6
                    ),
                    "discovery_summary_write_duration_seconds": round(
                        discovery_summary_write_duration_seconds, 6
                    ),
                    "discovery_report_write_duration_seconds": round(
                        discovery_report_write_duration_seconds, 6
                    ),
                },
            }
        )
        (run_dir / "timing-summary.json").write_text(
            updated_timing_summary.model_dump_json(indent=2), encoding="utf-8"
        )

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
    """Build the machine-readable summary for a saved discovery run."""

    pages = manifest.pages
    timing_summary = load_timing_summary(run_dir)
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
        if page.page_type.value in {"unknown", "admin_category", "admin_setting_page"}
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
        role_profile=manifest.role_profile,
        run_dir=str(run_dir),
        settle_strategy=manifest.settle_strategy,
        total_pages=manifest.visited_pages,
        unique_normalized_urls=len({page.normalized_url for page in pages}),
        unknown_pages=manifest.summary.unknown_pages,
        workflow_edge_count=manifest.summary.workflow_edge_count,
        workflow_candidate_edge_count=load_workflow_graph_metric(run_dir, "candidate_edge_count"),
        workflow_suppressed_edge_count=load_workflow_graph_metric(run_dir, "suppressed_edge_count"),
        workflow_deduplicated_pairs=load_workflow_graph_metric(run_dir, "deduplicated_pair_count"),
        workflow_compressed_edge_count=load_workflow_graph_metric(run_dir, "compressed_edge_count"),
        workflow_cluster_count=load_workflow_graph_metric(run_dir, "cluster_count"),
        workflow_edge_type_counts=load_workflow_edge_type_counts(run_dir),
        workflow_edge_weight_counts=load_workflow_edge_counts(run_dir, "edge_weight_counts"),
        workflow_edge_relevance_counts=load_workflow_edge_counts(run_dir, "edge_relevance_counts"),
        workflow_pre_dedup_edge_weight_counts=load_workflow_edge_counts(run_dir, "pre_dedup_edge_weight_counts"),
        workflow_pre_dedup_edge_relevance_counts=load_workflow_edge_counts(run_dir, "pre_dedup_edge_relevance_counts"),
        crawl_duration_seconds=(
            manifest.crawl_finished_at - manifest.crawl_started_at
        ).total_seconds(),
        average_page_duration_seconds=timing_summary.average_page_duration_seconds if timing_summary else 0.0,
        median_page_duration_seconds=timing_summary.median_page_duration_seconds if timing_summary else 0.0,
        page_stage_totals=timing_summary.page_stage_totals if timing_summary else {},
        run_stage_totals=timing_summary.run_stage_totals if timing_summary else {},
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
        slowest_pages=timing_summary.slowest_pages if timing_summary else slowest_pages,
        slowest_extraction_pages=timing_summary.slowest_extraction_pages if timing_summary else [],
        slowest_route_families=timing_summary.slowest_route_families if timing_summary else [],
        unknown_pages_detail=unknown_pages_detail,
        weak_classification_candidates=weak_candidates,
        exclusion_candidates=exclusion_candidates,
        newly_seen_route_families=newly_seen_route_families,
        top_task_edge_page_types=top_task_edge_page_types(run_dir, pages),
        top_high_value_edge_page_types=top_high_value_edge_page_types(run_dir, pages),
        noisy_admin_route_families=noisy_admin_route_families(run_dir, pages),
        top_compressed_route_families=top_compressed_route_families(run_dir),
        pages_with_most_compression=pages_with_most_compression(run_dir, pages),
        strongest_primary_pages=strongest_primary_pages(pages),
        workflow_families=load_workflow_families(run_dir),
        intent_populated_pages=sum(1 for page in pages if page.primary_page_intent.value != "unknown"),
        materially_changed_next_steps=load_materially_changed_next_steps(run_dir),
    )


def route_family(url: str) -> str:
    """Group a URL into a compact path family for summary reporting."""

    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if not parts:
        return "/"
    return "/" + "/".join(parts[:2])


def route_signature(url: str) -> str:
    """Return a route plus sorted query keys for query-heavy reporting."""

    parsed = urlparse(url)
    query_keys = sorted(key for key, _ in parse_qsl(parsed.query, keep_blank_values=True))
    if not query_keys:
        return parsed.path or "/"
    return f"{parsed.path}?{','.join(query_keys)}"


def find_latest_manifest(base_dir: Path) -> Path | None:
    """Return the newest `sitemap.json` under a run-root directory."""

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
    """Load a saved manifest when present, tolerating older enum names.

    Discovery summaries compare against earlier runs. This loader keeps that
    comparison working even when saved manifests predate small taxonomy or
    schema cleanups.
    """

    if path is None:
        return None
    manifest_path = Path(path)
    if not manifest_path.exists():
        return None
    raw_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for page in raw_data.get("pages", []):
        if isinstance(page, dict):
            if page.get("page_type") == "admin_settings":
                page["page_type"] = "admin_setting_page"
            page.pop("forms", None)
            page.pop("editors", None)
            page.pop("links", None)
            page.pop("buttons", None)
    summary = raw_data.get("summary")
    if isinstance(summary, dict):
        page_type_counts = summary.get("page_type_counts")
        if isinstance(page_type_counts, dict) and "admin_settings" in page_type_counts:
            admin_count = int(page_type_counts.pop("admin_settings") or 0)
            page_type_counts["admin_setting_page"] = page_type_counts.get("admin_setting_page", 0) + admin_count
    return SiteManifest.model_validate(raw_data)


def render_discovery_markdown(summary: DiscoverySummary) -> str:
    """Render a concise human-readable companion to `discovery-summary.json`."""

    lines = [
        "# Discovery Summary",
        "",
        f"- Site URL: `{summary.site_url}`",
        f"- Run directory: `{summary.run_dir}`",
        f"- Total pages: `{summary.total_pages}`",
        f"- Unique normalized URLs: `{summary.unique_normalized_urls}`",
        f"- Unknown pages: `{summary.unknown_pages}`",
        f"- Workflow edges: `{summary.workflow_edge_count}`",
        f"- Candidate workflow edges: `{summary.workflow_candidate_edge_count}`",
        f"- Suppressed workflow edges: `{summary.workflow_suppressed_edge_count}`",
        f"- Deduplicated source-target pairs: `{summary.workflow_deduplicated_pairs}`",
        f"- Compressed workflow edges: `{summary.workflow_compressed_edge_count}`",
        f"- Background clusters: `{summary.workflow_cluster_count}`",
        f"- Crawl duration (seconds): `{summary.crawl_duration_seconds}`",
        f"- Average page duration (seconds): `{summary.average_page_duration_seconds}`",
        f"- Median page duration (seconds): `{summary.median_page_duration_seconds}`",
        f"- Max depth reached: `{summary.max_depth_reached}`",
        "",
        "## Timing Breakdown",
        "",
        f"- Page stage totals: `{summary.page_stage_totals}`",
        f"- Run stage totals: `{summary.run_stage_totals}`",
        "",
        "## Workflow Signal",
        "",
        f"- Pre-dedup edge weights: `{summary.workflow_pre_dedup_edge_weight_counts}`",
        f"- Edge weights: `{summary.workflow_edge_weight_counts}`",
        f"- Pre-dedup edge relevance: `{summary.workflow_pre_dedup_edge_relevance_counts}`",
        f"- Edge relevance: `{summary.workflow_edge_relevance_counts}`",
        f"- Pages with populated primary intent: `{summary.intent_populated_pages}`",
        "",
        "## Top Route Families",
    ]
    for item in summary.top_route_families:
        lines.append(f"- `{item['route_family']}`: {item['count']}")
    lines.extend(["", "## Newly Seen Route Families"])
    for family in summary.newly_seen_route_families:
        lines.append(f"- `{family}`")
    lines.extend(["", "## Top Task Edge Page Types"])
    if summary.top_task_edge_page_types:
        for item in summary.top_task_edge_page_types:
            lines.append(f"- `{item['page_type']}`: {item['task_edge_count']}")
    else:
        lines.append("- None")
    lines.extend(["", "## Top High-Value Edge Page Types"])
    if summary.top_high_value_edge_page_types:
        for item in summary.top_high_value_edge_page_types:
            lines.append(f"- `{item['page_type']}`: {item['high_value_edge_count']}")
    else:
        lines.append("- None")
    lines.extend(["", "## Noisy Admin Route Families"])
    if summary.noisy_admin_route_families:
        for item in summary.noisy_admin_route_families:
            lines.append(f"- `{item['route_family']}`: {item['low_value_edge_count']}")
    else:
        lines.append("- None")
    lines.extend(["", "## Top Compressed Route Families"])
    if summary.top_compressed_route_families:
        for item in summary.top_compressed_route_families:
            lines.append(f"- `{item['family_key']}`: {item['count']}")
    else:
        lines.append("- None")
    lines.extend(["", "## Pages With Most Compression"])
    if summary.pages_with_most_compression:
        for item in summary.pages_with_most_compression:
            lines.append(f"- `{item['page_id']}`: {item['compressed_edge_count']}")
    else:
        lines.append("- None")
    lines.extend(["", "## Strongest Primary Pages"])
    if summary.strongest_primary_pages:
        for item in summary.strongest_primary_pages:
            lines.append(
                f"- `{item['page_id']}` (`{item['page_type']}`): {item['primary_page_intent']} / {item['task_relevance_score']}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Workflow Families"])
    if summary.workflow_families:
        for family in summary.workflow_families:
            lines.append(
                f"- `{family.family_label}`: {len(family.member_page_ids)} visited page(s), {len(family.descendants)} discovered descendant group(s)"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Materially Changed Next Steps"])
    if summary.materially_changed_next_steps:
        for item in summary.materially_changed_next_steps[:5]:
            lines.append(f"- `{item['page_id']}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Unknown Pages"])
    if summary.unknown_pages_detail:
        for item in summary.unknown_pages_detail:
            lines.append(f"- `{item['normalized_url']}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Slowest Route Families"])
    if summary.slowest_route_families:
        for item in summary.slowest_route_families[:5]:
            lines.append(
                f"- `{item['route_family']}`: avg {item['average_duration_seconds']}s over {item['page_count']} page(s)"
            )
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
    if summary.workflow_edge_relevance_counts.get("contextual", 0):
        actions.append("Review low-value contextual edges and generic route families to reduce graph noise.")
    if summary.workflow_cluster_count:
        actions.append("Inspect the largest background navigation clusters to decide whether more route families should be compressed.")
    if summary.page_type_counts.get("admin_category", 0) or summary.page_type_counts.get("admin_setting_page", 0):
        actions.append("Inspect whether any remaining admin subtypes are still too broad and need later decomposition.")
    return actions[:5]


def load_workflow_edge_type_counts(run_dir: Path) -> dict[str, int]:
    workflow_path = run_dir / "workflow-edges.json"
    if not workflow_path.exists():
        return {}
    raw = json.loads(workflow_path.read_text(encoding="utf-8"))
    return raw.get("edge_type_counts", {})


def load_timing_summary(run_dir: Path) -> CrawlTimingSummary | None:
    timing_path = run_dir / "timing-summary.json"
    if not timing_path.exists():
        return None
    return CrawlTimingSummary.model_validate_json(timing_path.read_text(encoding="utf-8"))


def load_workflow_edge_counts(run_dir: Path, key: str) -> dict[str, int]:
    raw = load_workflow_graph_raw(run_dir)
    return raw.get(key, {}) if raw else {}


def load_workflow_graph_metric(run_dir: Path, key: str) -> int:
    raw = load_workflow_graph_raw(run_dir)
    if not raw:
        return 0
    return int(raw.get(key, 0) or 0)


def load_materially_changed_next_steps(run_dir: Path) -> list[dict[str, object]]:
    raw = load_workflow_graph_raw(run_dir)
    if not raw:
        return []
    return raw.get("next_step_changed_pages", [])


def load_workflow_families(run_dir: Path) -> list[WorkflowFamilySummary]:
    raw = load_workflow_graph_raw(run_dir)
    if not raw:
        return []
    items = raw.get("workflow_families", [])
    if not isinstance(items, list):
        return []
    return [WorkflowFamilySummary.model_validate(item) for item in items if isinstance(item, dict)]


def load_workflow_graph_raw(run_dir: Path) -> dict[str, object]:
    workflow_path = run_dir / "workflow-edges.json"
    if not workflow_path.exists():
        return {}
    return json.loads(workflow_path.read_text(encoding="utf-8"))


def top_compressed_route_families(run_dir: Path) -> list[dict[str, int | str]]:
    raw = load_workflow_graph_raw(run_dir)
    counts = Counter(
        cluster.get("family_key", "unknown")
        for cluster in raw.get("background_clusters", [])
    )
    return [{"family_key": family_key, "count": count} for family_key, count in counts.most_common(5)]


def pages_with_most_compression(run_dir: Path, pages: list[PageRecord]) -> list[dict[str, int | str]]:
    raw = load_workflow_graph_raw(run_dir)
    counts = Counter()
    for cluster in raw.get("background_clusters", []):
        counts[cluster.get("source_page_id", "unknown")] += int(cluster.get("count", 0) or 0)
    page_type_by_id = {page.page_id: page.page_type.value for page in pages}
    return [
        {
            "page_id": page_id,
            "page_type": page_type_by_id.get(page_id, "unknown"),
            "compressed_edge_count": count,
        }
        for page_id, count in counts.most_common(5)
    ]


def top_task_edge_page_types(run_dir: Path, pages: list[PageRecord]) -> list[dict[str, int | str]]:
    workflow_path = run_dir / "workflow-edges.json"
    if not workflow_path.exists():
        return []
    raw = json.loads(workflow_path.read_text(encoding="utf-8"))
    page_type_by_id = {page.page_id: page.page_type.value for page in pages}
    counts = Counter(
        page_type_by_id.get(edge.get("from_page_id"), "unknown")
        for edge in raw.get("edges", [])
        if edge.get("edge_relevance") == "task"
    )
    return [
        {"page_type": page_type, "task_edge_count": count}
        for page_type, count in counts.most_common(5)
    ]


def top_high_value_edge_page_types(run_dir: Path, pages: list[PageRecord]) -> list[dict[str, int | str]]:
    workflow_path = run_dir / "workflow-edges.json"
    if not workflow_path.exists():
        return []
    raw = json.loads(workflow_path.read_text(encoding="utf-8"))
    page_type_by_id = {page.page_id: page.page_type.value for page in pages}
    counts = Counter(
        page_type_by_id.get(edge.get("from_page_id"), "unknown")
        for edge in raw.get("edges", [])
        if edge.get("edge_weight") == "high"
    )
    return [
        {"page_type": page_type, "high_value_edge_count": count}
        for page_type, count in counts.most_common(5)
    ]


def noisy_admin_route_families(run_dir: Path, pages: list[PageRecord]) -> list[dict[str, int | str]]:
    workflow_path = run_dir / "workflow-edges.json"
    if not workflow_path.exists():
        return []
    raw = json.loads(workflow_path.read_text(encoding="utf-8"))
    page_by_id = {page.page_id: page for page in pages}
    counts: Counter[str] = Counter()
    for edge in raw.get("edges", []):
        if edge.get("edge_weight") != "low":
            continue
        if edge.get("edge_relevance") not in {"navigation", "contextual"}:
            continue
        source_page = page_by_id.get(edge.get("from_page_id"))
        if source_page is None:
            continue
        if not source_page.page_type.value.startswith("admin_"):
            continue
        counts[route_family(source_page.normalized_url)] += 1
    return [
        {"route_family": family, "low_value_edge_count": count}
        for family, count in counts.most_common(5)
    ]


def strongest_primary_pages(pages: list[PageRecord]) -> list[dict[str, int | str]]:
    ranked_pages = sorted(
        pages,
        key=lambda page: (
            -(page.task_relevance_score or 0),
            page.page_id,
        ),
    )[:5]
    return [
        {
            "page_id": page.page_id,
            "page_type": page.page_type.value,
            "primary_page_intent": page.primary_page_intent.value,
            "task_relevance_score": page.task_relevance_score,
        }
        for page in ranked_pages
    ]
