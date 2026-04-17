# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

"""Helpers for side-by-side settle-strategy discovery comparisons.

The goal of this module is to keep settle comparisons small and explicit:
run the same bounded discovery crawl sequentially for a few strategies, then
summarize timing and artifact-quality differences in one inspectable report.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from moodle_sitemap.crawl import ProgressCallback
from moodle_sitemap.discovery import DiscoveryRunResult, run_discovery
from moodle_sitemap.models import SettleComparisonRun, SettleComparisonSummary, SettleStrategy


@dataclass(slots=True)
class SettleComparisonResult:
    """Paths and parsed summary emitted by one settle comparison run."""

    output_dir: Path
    summary: SettleComparisonSummary
    json_path: Path
    markdown_path: Path
    run_results: list[DiscoveryRunResult]


def create_settle_comparison_dir(base_dir: str | Path = "settle-comparisons") -> Path:
    """Create a timestamped directory for one settle-strategy comparison."""

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    output_dir = Path(base_dir) / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    return output_dir


def compare_settle_strategies(
    *,
    config_path: str | Path,
    strategies: list[SettleStrategy],
    max_pages: int,
    max_depth: int | None = 4,
    base_dir: str | Path = "settle-comparisons",
    discovery_base_dir: str | Path = "discovery-runs",
    progress_callback: ProgressCallback | None = None,
) -> SettleComparisonResult:
    """Run sequential discovery crawls with multiple settle strategies."""

    unique_strategies = list(dict.fromkeys(strategies))
    if not unique_strategies:
        raise ValueError("At least one settle strategy is required.")

    run_results: list[DiscoveryRunResult] = []
    for strategy in unique_strategies:
        run_results.append(
            run_discovery(
                config_path=config_path,
                max_pages=max_pages,
                max_depth=max_depth,
                settle_strategy=strategy,
                base_dir=discovery_base_dir,
                progress_callback=progress_callback,
            )
        )

    summary = build_settle_comparison_summary(
        config_path=config_path,
        max_pages=max_pages,
        max_depth=max_depth,
        run_results=run_results,
    )

    output_dir = create_settle_comparison_dir(base_dir)
    json_path = output_dir / "settle-comparison.json"
    markdown_path = output_dir / "settle-comparison.md"
    json_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_settle_comparison_markdown(summary), encoding="utf-8")

    return SettleComparisonResult(
        output_dir=output_dir,
        summary=summary,
        json_path=json_path,
        markdown_path=markdown_path,
        run_results=run_results,
    )


def build_settle_comparison_summary(
    *,
    config_path: str | Path,
    max_pages: int,
    max_depth: int | None,
    run_results: list[DiscoveryRunResult],
) -> SettleComparisonSummary:
    """Aggregate per-strategy discovery results into one comparison summary."""

    strategies = [build_strategy_summary(result) for result in run_results]
    if not strategies:
        raise ValueError("At least one discovery result is required.")

    baseline = strategies[0]
    baseline_result = run_results[0]
    fastest = min(strategies, key=lambda item: item.crawl_duration_seconds)
    strategy_deltas = [
        build_strategy_delta(baseline, candidate) for candidate in strategies[1:]
    ]
    crawl_surface_deltas = [
        build_crawl_surface_delta(baseline_result, candidate_result)
        for candidate_result in run_results[1:]
    ]
    quality_regressions = [
        delta
        for delta in strategy_deltas
        if delta["unknown_page_delta"] > 0
        or delta["page_delta"] < 0
        or delta["workflow_edge_delta"] < 0
        or delta["next_step_page_delta"] < 0
    ]
    recommended_strategy, recommendation_reason = choose_recommended_strategy(
        baseline=baseline,
        strategies=strategies,
    )

    return SettleComparisonSummary(
        config_path=str(config_path),
        max_pages=max_pages,
        max_depth=max_depth,
        strategies=strategies,
        baseline_strategy=baseline.settle_strategy,
        fastest_strategy=fastest.settle_strategy,
        recommended_strategy=recommended_strategy,
        recommendation_reason=recommendation_reason,
        strategy_deltas=strategy_deltas,
        crawl_surface_deltas=crawl_surface_deltas,
        quality_regressions=quality_regressions,
    )


def build_strategy_summary(result: DiscoveryRunResult) -> SettleComparisonRun:
    """Extract the comparison-relevant metrics from one discovery result."""

    summary = result.summary
    return SettleComparisonRun(
        settle_strategy=summary.settle_strategy,
        run_dir=str(result.run_dir),
        total_pages=summary.total_pages,
        unknown_pages=summary.unknown_pages,
        workflow_edge_count=summary.workflow_edge_count,
        next_step_page_count=sum(1 for page in result.manifest.pages if page.next_steps),
        intent_populated_pages=sum(
            1 for page in result.manifest.pages if page.primary_page_intent.value != "unknown"
        ),
        crawl_duration_seconds=summary.crawl_duration_seconds,
        average_page_duration_seconds=summary.average_page_duration_seconds,
        median_page_duration_seconds=summary.median_page_duration_seconds,
        navigation_duration_seconds=summary.page_stage_totals.get("navigation_duration_seconds", 0.0),
        settle_duration_seconds=summary.page_stage_totals.get("settle_duration_seconds", 0.0),
        extraction_duration_seconds=summary.page_stage_totals.get("extraction_duration_seconds", 0.0),
        write_duration_seconds=summary.page_stage_totals.get("write_duration_seconds", 0.0),
        page_type_counts=summary.page_type_counts,
        workflow_edge_weight_counts=summary.workflow_edge_weight_counts,
        workflow_edge_relevance_counts=summary.workflow_edge_relevance_counts,
    )


def build_strategy_delta(
    baseline: SettleComparisonRun,
    candidate: SettleComparisonRun,
) -> dict[str, object]:
    """Summarize the quality and timing deltas relative to the baseline."""

    return {
        "strategy": candidate.settle_strategy.value,
        "crawl_duration_delta_seconds": round(
            candidate.crawl_duration_seconds - baseline.crawl_duration_seconds, 6
        ),
        "average_page_duration_delta_seconds": round(
            candidate.average_page_duration_seconds - baseline.average_page_duration_seconds,
            6,
        ),
        "settle_duration_delta_seconds": round(
            candidate.settle_duration_seconds - baseline.settle_duration_seconds,
            6,
        ),
        "page_delta": candidate.total_pages - baseline.total_pages,
        "unknown_page_delta": candidate.unknown_pages - baseline.unknown_pages,
        "workflow_edge_delta": candidate.workflow_edge_count - baseline.workflow_edge_count,
        "next_step_page_delta": candidate.next_step_page_count - baseline.next_step_page_count,
        "intent_populated_page_delta": candidate.intent_populated_pages - baseline.intent_populated_pages,
        "page_type_count_deltas": {
            page_type: candidate.page_type_counts.get(page_type, 0) - baseline.page_type_counts.get(page_type, 0)
            for page_type in sorted(set(baseline.page_type_counts) | set(candidate.page_type_counts))
            if candidate.page_type_counts.get(page_type, 0) != baseline.page_type_counts.get(page_type, 0)
        },
    }


def build_crawl_surface_delta(
    baseline_result: DiscoveryRunResult,
    candidate_result: DiscoveryRunResult,
) -> dict[str, object]:
    """Summarize crawl-surface overlap relative to the baseline run."""

    baseline_pages = {page.normalized_url for page in baseline_result.manifest.pages}
    candidate_pages = {page.normalized_url for page in candidate_result.manifest.pages}
    shared_pages = baseline_pages & candidate_pages
    baseline_only_pages = sorted(baseline_pages - candidate_pages)
    candidate_only_pages = sorted(candidate_pages - baseline_pages)

    baseline_families = {route_family(url) for url in baseline_pages}
    candidate_families = {route_family(url) for url in candidate_pages}

    return {
        "strategy": candidate_result.summary.settle_strategy.value,
        "shared_normalized_url_count": len(shared_pages),
        "baseline_only_page_count": len(baseline_only_pages),
        "candidate_only_page_count": len(candidate_only_pages),
        "baseline_only_pages": baseline_only_pages[:10],
        "candidate_only_pages": candidate_only_pages[:10],
        "shared_route_family_count": len(baseline_families & candidate_families),
        "baseline_only_route_family_count": len(baseline_families - candidate_families),
        "candidate_only_route_family_count": len(candidate_families - baseline_families),
        "baseline_only_route_families": sorted(baseline_families - candidate_families)[:10],
        "candidate_only_route_families": sorted(candidate_families - baseline_families)[:10],
        "shared_page_type_count": len(
            set(page.page_type.value for page in baseline_result.manifest.pages)
            & set(page.page_type.value for page in candidate_result.manifest.pages)
        ),
    }


def choose_recommended_strategy(
    *,
    baseline: SettleComparisonRun,
    strategies: list[SettleComparisonRun],
) -> tuple[SettleStrategy, str]:
    """Pick the fastest strategy that does not show obvious quality regression."""

    acceptable = [
        strategy
        for strategy in strategies
        if strategy.total_pages >= baseline.total_pages
        and strategy.unknown_pages <= baseline.unknown_pages
        and strategy.workflow_edge_count >= baseline.workflow_edge_count
        and strategy.next_step_page_count >= baseline.next_step_page_count
    ]
    if acceptable:
        winner = min(acceptable, key=lambda item: item.crawl_duration_seconds)
        if winner.settle_strategy == baseline.settle_strategy:
            return winner.settle_strategy, "Baseline remained the safest measured option."
        return (
            winner.settle_strategy,
            "Measured faster without reducing page count, workflow edges, unknown-page quality, or next-step coverage.",
        )
    return baseline.settle_strategy, "Lighter strategies showed quality regressions relative to the baseline."


def render_settle_comparison_markdown(summary: SettleComparisonSummary) -> str:
    """Render a short human-readable settle comparison report."""

    lines = [
        "# Settle Comparison",
        "",
        f"- Config: `{summary.config_path}`",
        f"- Max pages: `{summary.max_pages}`",
        f"- Max depth: `{summary.max_depth}`",
        f"- Baseline strategy: `{summary.baseline_strategy.value if summary.baseline_strategy else 'n/a'}`",
        f"- Fastest strategy: `{summary.fastest_strategy.value if summary.fastest_strategy else 'n/a'}`",
        f"- Recommended strategy: `{summary.recommended_strategy.value if summary.recommended_strategy else 'n/a'}`",
        "",
    ]
    if summary.recommendation_reason:
        lines.extend(["## Recommendation", "", summary.recommendation_reason, ""])

    lines.extend(["## Strategies", ""])
    for strategy in summary.strategies:
        lines.extend(
            [
                f"- `{strategy.settle_strategy.value}`: crawl `{strategy.crawl_duration_seconds:.2f}s`, "
                f"pages `{strategy.total_pages}`, unknown `{strategy.unknown_pages}`, "
                f"edges `{strategy.workflow_edge_count}`, next-step pages `{strategy.next_step_page_count}`",
            ]
        )

    if summary.strategy_deltas:
        lines.extend(["", "## Deltas vs baseline", ""])
        for delta in summary.strategy_deltas:
            lines.append(
                f"- `{delta['strategy']}`: total `{delta['crawl_duration_delta_seconds']:+.2f}s`, "
                f"settle `{delta['settle_duration_delta_seconds']:+.2f}s`, "
                f"pages `{delta['page_delta']:+d}`, unknown `{delta['unknown_page_delta']:+d}`, "
                f"edges `{delta['workflow_edge_delta']:+d}`"
            )

    if summary.crawl_surface_deltas:
        lines.extend(["", "## Crawl surface overlap", ""])
        for delta in summary.crawl_surface_deltas:
            lines.append(
                f"- `{delta['strategy']}`: shared pages `{delta['shared_normalized_url_count']}`, "
                f"baseline-only `{delta['baseline_only_page_count']}`, "
                f"candidate-only `{delta['candidate_only_page_count']}`, "
                f"shared route families `{delta['shared_route_family_count']}`"
            )

    if summary.quality_regressions:
        lines.extend(["", "## Quality regressions", ""])
        for regression in summary.quality_regressions:
            lines.append(
                f"- `{regression['strategy']}` regressed pages `{regression['page_delta']:+d}`, "
                f"unknown `{regression['unknown_page_delta']:+d}`, edges `{regression['workflow_edge_delta']:+d}`, "
                f"next-step pages `{regression['next_step_page_delta']:+d}`"
            )

    lines.append("")
    return "\n".join(lines)


def route_family(url: str) -> str:
    """Group a URL into a compact path family for surface overlap summaries."""

    parts = [part for part in urlparse(url).path.strip("/").split("/") if part]
    if not parts:
        return "/"
    return "/" + "/".join(parts[:2])
