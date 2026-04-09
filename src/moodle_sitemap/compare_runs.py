from __future__ import annotations

"""Compare two saved crawl or discovery runs.

The comparison layer is intentionally artifact-driven: it reads the saved
manifest and workflow graph for each run and then explains how visibility,
affordances, next steps, and safety differ.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

from moodle_sitemap.models import EdgeRelevance, RunComparisonSummary, SiteManifest, WorkflowGraph


@dataclass(slots=True)
class RunCompareResult:
    """File paths and parsed summary produced by `compare_runs`."""

    output_dir: Path
    json_path: Path
    markdown_path: Path
    summary: RunComparisonSummary


def create_compare_run_dir(base_dir: str | Path = "comparison-runs") -> Path:
    """Create a unique timestamped directory for a comparison report."""

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    root = Path(base_dir)
    for suffix in ["", "-2", "-3", "-4", "-5"]:
        output_dir = root / f"{timestamp}{suffix}"
        try:
            output_dir.mkdir(parents=True, exist_ok=False)
            return output_dir
        except FileExistsError:
            continue
    raise ValueError(f"Could not create unique comparison run directory under {root}")


def compare_runs(
    *,
    left_run_dir: str | Path,
    right_run_dir: str | Path,
    base_dir: str | Path = "comparison-runs",
) -> RunCompareResult:
    """Compare two saved runs and write JSON/Markdown comparison artifacts."""

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
    filename_stem = comparison_filename_stem(summary.left_role_profile, summary.right_role_profile)
    json_path = output_dir / f"{filename_stem}.json"
    json_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    markdown_path = output_dir / f"{filename_stem}.md"
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
    """Build the structured difference summary between two saved runs."""

    left_pages = {page.normalized_url: page for page in left_manifest.pages}
    right_pages = {page.normalized_url: page for page in right_manifest.pages}
    shared_urls = sorted(set(left_pages) & set(right_pages))

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
        shared_page_count=len(shared_urls),
        left_workflow_edges=left_graph.total_edges if left_graph else 0,
        right_workflow_edges=right_graph.total_edges if right_graph else 0,
        left_task_edges=count_task_edges(left_graph),
        right_task_edges=count_task_edges(right_graph),
        page_type_count_deltas=page_type_count_deltas,
        pages_only_in_left=sorted(set(left_pages) - set(right_pages)),
        pages_only_in_right=sorted(set(right_pages) - set(left_pages)),
        edge_signatures_only_in_left=sorted(left_edge_signatures - right_edge_signatures),
        edge_signatures_only_in_right=sorted(right_edge_signatures - left_edge_signatures),
        affordance_differences=build_affordance_differences(left_pages, right_pages),
        next_step_differences=build_next_step_differences(left_pages, right_pages),
        safety_differences=build_safety_differences(left_pages, right_pages),
    )


def build_affordance_differences(left_pages: dict[str, object], right_pages: dict[str, object]) -> list[dict[str, object]]:
    """Summarize action-label differences on shared pages."""

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


def build_next_step_differences(left_pages: dict[str, object], right_pages: dict[str, object]) -> list[dict[str, object]]:
    """Summarize `next_steps` differences on shared pages."""

    differences: list[dict[str, object]] = []
    common_urls = sorted(set(left_pages) & set(right_pages))
    for url in common_urls:
        left_page = left_pages[url]
        right_page = right_pages[url]
        left_next_steps = {step.label or step.target_url for step in left_page.next_steps}
        right_next_steps = {step.label or step.target_url for step in right_page.next_steps}
        only_left = sorted(left_next_steps - right_next_steps)
        only_right = sorted(right_next_steps - left_next_steps)
        if not only_left and not only_right:
            continue
        differences.append(
            {
                "normalized_url": url,
                "page_type_left": left_page.page_type.value,
                "page_type_right": right_page.page_type.value,
                "next_steps_only_in_left": only_left[:8],
                "next_steps_only_in_right": only_right[:8],
            }
        )
    return differences[:20]


def build_safety_differences(left_pages: dict[str, object], right_pages: dict[str, object]) -> list[dict[str, object]]:
    """Summarize page-level safety differences on shared pages."""

    differences: list[dict[str, object]] = []
    common_urls = sorted(set(left_pages) & set(right_pages))
    for url in common_urls:
        left_page = left_pages[url]
        right_page = right_pages[url]
        left_safety = left_page.safety
        right_safety = right_page.safety
        if (
            left_safety.page_risk_level == right_safety.page_risk_level
            and left_safety.contains_mutating_actions == right_safety.contains_mutating_actions
            and left_safety.contains_destructive_actions == right_safety.contains_destructive_actions
            and left_safety.mutating_action_count == right_safety.mutating_action_count
        ):
            continue
        differences.append(
            {
                "normalized_url": url,
                "page_type_left": left_page.page_type.value,
                "page_type_right": right_page.page_type.value,
                "left_risk_level": left_safety.page_risk_level.value,
                "right_risk_level": right_safety.page_risk_level.value,
                "left_mutating_action_count": left_safety.mutating_action_count,
                "right_mutating_action_count": right_safety.mutating_action_count,
                "left_contains_destructive_actions": left_safety.contains_destructive_actions,
                "right_contains_destructive_actions": right_safety.contains_destructive_actions,
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


def count_task_edges(graph: WorkflowGraph | None) -> int:
    if graph is None:
        return 0
    return sum(1 for edge in graph.edges if edge.edge_relevance == EdgeRelevance.TASK)


def comparison_filename_stem(left_role: str, right_role: str) -> str:
    return f"role-compare-{slugify_role(left_role)}-vs-{slugify_role(right_role)}"


def slugify_role(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return cleaned.strip("-") or "unlabeled"


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
        f"- Shared pages: `{summary.shared_page_count}`",
        f"- Left workflow edges: `{summary.left_workflow_edges}`",
        f"- Right workflow edges: `{summary.right_workflow_edges}`",
        f"- Left task edges: `{summary.left_task_edges}`",
        f"- Right task edges: `{summary.right_task_edges}`",
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
    lines.extend(["", "## Affordance Differences"])
    if summary.affordance_differences:
        for item in summary.affordance_differences[:5]:
            lines.append(
                f"- `{item['normalized_url']}` left-only actions={item['actions_only_in_left']} "
                f"right-only actions={item['actions_only_in_right']}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Next Step Differences"])
    if summary.next_step_differences:
        for item in summary.next_step_differences[:5]:
            lines.append(
                f"- `{item['normalized_url']}` left-only next steps={item['next_steps_only_in_left']} "
                f"right-only next steps={item['next_steps_only_in_right']}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Safety Differences"])
    if summary.safety_differences:
        for item in summary.safety_differences[:5]:
            lines.append(
                f"- `{item['normalized_url']}` risk `{item['left_risk_level']}` -> `{item['right_risk_level']}`, "
                f"mutating actions `{item['left_mutating_action_count']}` -> `{item['right_mutating_action_count']}`"
            )
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"
