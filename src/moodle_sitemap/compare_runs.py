from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from moodle_sitemap.models import RunComparisonSummary, SiteManifest, WorkflowGraph


@dataclass(slots=True)
class RunCompareResult:
    output_dir: Path
    json_path: Path
    markdown_path: Path
    summary: RunComparisonSummary


def create_compare_run_dir(base_dir: str | Path = "comparison-runs") -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    output_dir = Path(base_dir) / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    return output_dir


def compare_runs(
    *,
    left_run_dir: str | Path,
    right_run_dir: str | Path,
    base_dir: str | Path = "comparison-runs",
) -> RunCompareResult:
    left_dir = Path(left_run_dir)
    right_dir = Path(right_run_dir)
    left_manifest = load_manifest(left_dir / "sitemap.json")
    right_manifest = load_manifest(right_dir / "sitemap.json")
    left_graph = load_workflow_graph(left_dir / "workflow-edges.json")
    right_graph = load_workflow_graph(right_dir / "workflow-edges.json")

    summary = build_run_comparison_summary(
        left_run_dir=left_dir,
        right_run_dir=right_dir,
        left_manifest=left_manifest,
        right_manifest=right_manifest,
        left_graph=left_graph,
        right_graph=right_graph,
    )
    output_dir = create_compare_run_dir(base_dir)
    json_path = output_dir / "role-compare.json"
    json_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    markdown_path = output_dir / "role-compare.md"
    markdown_path.write_text(render_run_comparison_markdown(summary), encoding="utf-8")
    return RunCompareResult(
        output_dir=output_dir,
        json_path=json_path,
        markdown_path=markdown_path,
        summary=summary,
    )


def build_run_comparison_summary(
    *,
    left_run_dir: Path,
    right_run_dir: Path,
    left_manifest: SiteManifest,
    right_manifest: SiteManifest,
    left_graph: WorkflowGraph | None,
    right_graph: WorkflowGraph | None,
) -> RunComparisonSummary:
    left_pages = {page.normalized_url: page for page in left_manifest.pages}
    right_pages = {page.normalized_url: page for page in right_manifest.pages}

    page_type_count_deltas: dict[str, dict[str, int]] = {}
    all_page_types = sorted(
        set(left_manifest.summary.page_type_counts) | set(right_manifest.summary.page_type_counts)
    )
    for page_type in all_page_types:
        left_count = left_manifest.summary.page_type_counts.get(page_type, 0)
        right_count = right_manifest.summary.page_type_counts.get(page_type, 0)
        page_type_count_deltas[page_type] = {
            "left": left_count,
            "right": right_count,
            "delta": right_count - left_count,
        }

    left_edge_signatures = edge_signatures(left_graph, left_pages)
    right_edge_signatures = edge_signatures(right_graph, right_pages)

    return RunComparisonSummary(
        left_run_dir=str(left_run_dir),
        right_run_dir=str(right_run_dir),
        left_role_profile=left_manifest.role_profile,
        right_role_profile=right_manifest.role_profile,
        left_total_pages=left_manifest.visited_pages,
        right_total_pages=right_manifest.visited_pages,
        left_workflow_edges=left_graph.total_edges if left_graph else 0,
        right_workflow_edges=right_graph.total_edges if right_graph else 0,
        page_type_count_deltas=page_type_count_deltas,
        pages_only_in_left=sorted(set(left_pages) - set(right_pages)),
        pages_only_in_right=sorted(set(right_pages) - set(left_pages)),
        edge_signatures_only_in_left=sorted(left_edge_signatures - right_edge_signatures),
        edge_signatures_only_in_right=sorted(right_edge_signatures - left_edge_signatures),
        affordance_differences=build_affordance_differences(left_pages, right_pages),
    )


def build_affordance_differences(left_pages: dict[str, object], right_pages: dict[str, object]) -> list[dict[str, object]]:
    differences: list[dict[str, object]] = []
    common_urls = sorted(set(left_pages) & set(right_pages))
    for url in common_urls:
        left_page = left_pages[url]
        right_page = right_pages[url]
        left_actions = {action.label for action in left_page.affordances.actions}
        right_actions = {action.label for action in right_page.affordances.actions}
        only_left = sorted(left_actions - right_actions)
        only_right = sorted(right_actions - left_actions)
        if not only_left and not only_right:
            continue
        differences.append(
            {
                "normalized_url": url,
                "page_type_left": left_page.page_type.value,
                "page_type_right": right_page.page_type.value,
                "actions_only_in_left": only_left[:10],
                "actions_only_in_right": only_right[:10],
            }
        )
    return differences[:20]


def edge_signatures(graph: WorkflowGraph | None, pages_by_url: dict[str, object]) -> set[str]:
    if graph is None:
        return set()
    page_ids_to_urls = {page.page_id: page.normalized_url for page in pages_by_url.values()}
    signatures: set[str] = set()
    for edge in graph.edges:
        from_url = page_ids_to_urls.get(edge.from_page_id, edge.from_page_id)
        signatures.add(f"{edge.edge_type.value}:{from_url}->{edge.target_url}")
    return signatures


def load_manifest(path: Path) -> SiteManifest:
    return SiteManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_workflow_graph(path: Path) -> WorkflowGraph | None:
    if not path.exists():
        return None
    return WorkflowGraph.model_validate_json(path.read_text(encoding="utf-8"))


def render_run_comparison_markdown(summary: RunComparisonSummary) -> str:
    lines = [
        "# Run Comparison",
        "",
        f"- Left run: `{summary.left_run_dir}` ({summary.left_role_profile})",
        f"- Right run: `{summary.right_run_dir}` ({summary.right_role_profile})",
        f"- Left pages: `{summary.left_total_pages}`",
        f"- Right pages: `{summary.right_total_pages}`",
        f"- Left workflow edges: `{summary.left_workflow_edges}`",
        f"- Right workflow edges: `{summary.right_workflow_edges}`",
        "",
        "## Pages Only In Left",
    ]
    if summary.pages_only_in_left:
        for item in summary.pages_only_in_left[:20]:
            lines.append(f"- `{item}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Pages Only In Right"])
    if summary.pages_only_in_right:
        for item in summary.pages_only_in_right[:20]:
            lines.append(f"- `{item}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Edge Differences"])
    lines.append(f"- Only in left: `{len(summary.edge_signatures_only_in_left)}`")
    lines.append(f"- Only in right: `{len(summary.edge_signatures_only_in_right)}`")
    return "\n".join(lines) + "\n"
