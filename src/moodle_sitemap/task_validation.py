from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json

from moodle_sitemap.models import (
    EdgeRelevance,
    EdgeWeight,
    LikelyIntent,
    PageRecord,
    PageType,
    SiteManifest,
    TaskSpec,
    TaskSpecList,
    TaskValidationStatus,
    TaskValidationSummary,
    TaskValidationTaskResult,
    WorkflowEdge,
    WorkflowGraph,
)


@dataclass(slots=True)
class TaskValidationRunResult:
    output_dir: Path
    json_path: Path
    markdown_path: Path
    summary: TaskValidationSummary


def create_task_validation_run_dir(base_dir: str | Path = "task-validation-runs") -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    root = Path(base_dir)
    for suffix in ["", "-2", "-3", "-4", "-5"]:
        output_dir = root / f"{timestamp}{suffix}"
        try:
            output_dir.mkdir(parents=True, exist_ok=False)
            return output_dir
        except FileExistsError:
            continue
    raise ValueError(f"Could not create unique task validation directory under {root}")


def load_task_specs(path: str | Path) -> TaskSpecList:
    spec_path = Path(path)
    try:
        return TaskSpecList.model_validate_json(spec_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Task spec file not found: {spec_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in task spec file {spec_path}: {exc}") from exc


def validate_tasks_for_run(
    *,
    run_dir: str | Path,
    tasks_path: str | Path,
    base_dir: str | Path = "task-validation-runs",
) -> TaskValidationRunResult:
    run_path = Path(run_dir)
    manifest = load_manifest(run_path / "sitemap.json")
    workflow_graph = load_workflow_graph(run_path / "workflow-edges.json")
    task_specs = load_task_specs(tasks_path)
    matching_tasks = [task for task in task_specs.tasks if task.role_profile == manifest.role_profile]

    results = [
        evaluate_task(task=task, manifest=manifest, workflow_graph=workflow_graph)
        for task in matching_tasks
    ]
    summary = TaskValidationSummary(
        site_url=manifest.site_url,
        role_profile=manifest.role_profile,
        run_dir=str(run_path),
        tasks_file=str(tasks_path),
        total_tasks=len(matching_tasks),
        pass_count=sum(1 for result in results if result.status == TaskValidationStatus.PASS),
        partial_count=sum(1 for result in results if result.status == TaskValidationStatus.PARTIAL),
        fail_count=sum(1 for result in results if result.status == TaskValidationStatus.FAIL),
        results=results,
    )

    output_dir = create_task_validation_run_dir(base_dir)
    json_path = output_dir / "task-validation.json"
    json_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    markdown_path = output_dir / "task-validation.md"
    markdown_path.write_text(render_task_validation_markdown(summary), encoding="utf-8")
    return TaskValidationRunResult(
        output_dir=output_dir,
        json_path=json_path,
        markdown_path=markdown_path,
        summary=summary,
    )


def evaluate_task(
    *,
    task: TaskSpec,
    manifest: SiteManifest,
    workflow_graph: WorkflowGraph | None,
) -> TaskValidationTaskResult:
    pages_by_id = {page.page_id: page for page in manifest.pages}
    start_page = choose_start_page(task, manifest.pages)
    target_pages = find_target_pages(task, manifest.pages)
    target_page_ids = [page.page_id for page in target_pages]
    result = TaskValidationTaskResult(
        task_id=task.task_id,
        role_profile=task.role_profile,
        status=TaskValidationStatus.FAIL,
        starting_page_id=start_page.page_id if start_page else None,
        target_page_ids=target_page_ids,
        discovered_target=bool(target_pages),
        target_page_types=sorted({page.page_type.value for page in target_pages}),
    )

    if start_page is None:
        result.blockers.append("starting-page-not-found")
        return result
    if not target_pages:
        result.blockers.append("target-page-not-found")
        return result

    path_edges = find_best_path(
        workflow_graph=workflow_graph,
        start_page_id=start_page.page_id,
        target_page_ids=set(target_page_ids),
    )
    if path_edges is None:
        result.status = TaskValidationStatus.PARTIAL
        result.blockers.append("no-plausible-path-in-graph")
    else:
        path_page_ids = [start_page.page_id]
        for edge in path_edges:
            if edge.to_page_id:
                path_page_ids.append(edge.to_page_id)
        result.candidate_path_page_ids = path_page_ids
        result.candidate_path_urls = [pages_by_id[page_id].normalized_url for page_id in path_page_ids if page_id in pages_by_id]
        result.candidate_path_page_types = [pages_by_id[page_id].page_type.value for page_id in path_page_ids if page_id in pages_by_id]
        result.path_length = len(path_edges)
        result.path_quality_score = score_path_quality(path_edges)
        result.next_step_support_score = score_next_step_support(start_page, path_edges)
        result.next_steps_helpful = result.next_step_support_score >= 60

    target_affordance_support = score_affordance_support(task, target_pages)
    result.affordance_support_score = target_affordance_support
    result.key_affordances = collect_key_affordances(task, target_pages)
    result.safety_notes = collect_safety_notes(target_pages)

    if path_edges is None:
        if target_affordance_support >= 60:
            result.status = TaskValidationStatus.PARTIAL
            result.notes.append("target-found-with-supporting-affordances-but-path-is-weak")
        else:
            result.status = TaskValidationStatus.FAIL
    else:
        if result.path_quality_score >= 60 and target_affordance_support >= 50:
            result.status = TaskValidationStatus.PASS
        elif result.path_quality_score >= 35 or target_affordance_support >= 40:
            result.status = TaskValidationStatus.PARTIAL
        else:
            result.status = TaskValidationStatus.FAIL

    expected_types = {page_type.value for page_type in task.expected_intermediate_page_types}
    if expected_types and result.candidate_path_page_types:
        found = expected_types & set(result.candidate_path_page_types[1:-1])
        if found:
            result.notes.append(f"expected-intermediate-types-found: {sorted(found)}")
        else:
            result.notes.append("expected-intermediate-types-not-found")

    if result.next_steps_helpful:
        result.notes.append("next-steps-support-the-first-hop")
    elif path_edges:
        result.notes.append("path-exists-but-next-steps-do-not-clearly-surface-it")

    return result


def choose_start_page(task: TaskSpec, pages: list[PageRecord]) -> PageRecord | None:
    if task.starting_url_contains:
        for page in pages:
            if task.starting_url_contains in page.normalized_url:
                return page
    if task.starting_page_type:
        for page in pages:
            if page.page_type == task.starting_page_type:
                return page
    return None


def find_target_pages(task: TaskSpec, pages: list[PageRecord]) -> list[PageRecord]:
    matches: list[PageRecord] = []
    for page in pages:
        if task.target_page_type and page.page_type != task.target_page_type:
            continue
        if task.target_route_family and not route_family(page.normalized_url).startswith(task.target_route_family):
            continue
        if task.target_url_contains and not all(needle in page.normalized_url for needle in task.target_url_contains):
            continue
        matches.append(page)
    return matches


def route_family(url: str) -> str:
    path = url.split("://", 1)[-1]
    if "/" not in path:
        return "/"
    return "/" + path.split("/", 1)[1].split("?", 1)[0]


def find_best_path(
    *,
    workflow_graph: WorkflowGraph | None,
    start_page_id: str,
    target_page_ids: set[str],
) -> list[WorkflowEdge] | None:
    if start_page_id in target_page_ids:
        return []
    if workflow_graph is None:
        return None

    edges_by_source: dict[str, list[WorkflowEdge]] = defaultdict(list)
    for edge in workflow_graph.edges:
        if edge.to_page_id:
            edges_by_source[edge.from_page_id].append(edge)

    queue: deque[tuple[str, list[WorkflowEdge]]] = deque([(start_page_id, [])])
    visited = {start_page_id}
    while queue:
        current_page_id, path_edges = queue.popleft()
        for edge in sorted(edges_by_source.get(current_page_id, []), key=edge_sort_key):
            if edge.to_page_id is None or edge.to_page_id in visited:
                continue
            next_path = [*path_edges, edge]
            if edge.to_page_id in target_page_ids:
                return next_path
            visited.add(edge.to_page_id)
            queue.append((edge.to_page_id, next_path))
    return None


def edge_sort_key(edge: WorkflowEdge) -> tuple[int, int, float]:
    relevance_rank = {
        EdgeRelevance.TASK: 0,
        EdgeRelevance.SUPPORT: 1,
        EdgeRelevance.NAVIGATION: 2,
        EdgeRelevance.CONTEXTUAL: 3,
    }[edge.edge_relevance]
    weight_rank = {
        EdgeWeight.HIGH: 0,
        EdgeWeight.MEDIUM: 1,
        EdgeWeight.LOW: 2,
    }[edge.edge_weight]
    confidence = -(edge.confidence or 0.0)
    return (relevance_rank, weight_rank, confidence)


def score_path_quality(edges: list[WorkflowEdge]) -> int:
    if not edges:
        return 100
    score = 100
    for edge in edges:
        score -= {
            EdgeRelevance.TASK: 4,
            EdgeRelevance.SUPPORT: 8,
            EdgeRelevance.NAVIGATION: 14,
            EdgeRelevance.CONTEXTUAL: 22,
        }[edge.edge_relevance]
        score -= {
            EdgeWeight.HIGH: 2,
            EdgeWeight.MEDIUM: 6,
            EdgeWeight.LOW: 10,
        }[edge.edge_weight]
    return max(0, min(100, score))


def score_next_step_support(start_page: PageRecord, path_edges: list[WorkflowEdge]) -> int:
    if not path_edges:
        return 100
    first_edge = path_edges[0]
    labels = {step.label for step in start_page.next_steps if step.label}
    urls = {step.target_url for step in start_page.next_steps}
    if first_edge.target_url in urls:
        return 100
    if first_edge.source_affordance_label and first_edge.source_affordance_label in labels:
        return 85
    return 20


def score_affordance_support(task: TaskSpec, target_pages: list[PageRecord]) -> int:
    if not target_pages:
        return 0
    if not task.required_affordance_intents:
        return 70
    intents = set(task.required_affordance_intents)
    best = 0
    for page in target_pages:
        page_intents = {
            action.likely_intent for action in page.affordances.actions
        } | {
            form.likely_intent for form in page.affordances.forms
        } | {
            nav.likely_intent for nav in page.affordances.navigation
        }
        overlap = len(intents & page_intents)
        if overlap == 0:
            continue
        best = max(best, min(100, 40 + overlap * 30))
    return best


def collect_key_affordances(task: TaskSpec, target_pages: list[PageRecord]) -> list[str]:
    labels: list[str] = []
    preferred_intents = set(task.required_affordance_intents)
    for page in target_pages[:3]:
        for action in page.affordances.actions:
            if len(labels) >= 8:
                return labels
            if preferred_intents and action.likely_intent not in preferred_intents:
                continue
            labels.append(action.label)
        for form in page.affordances.forms:
            if len(labels) >= 8:
                return labels
            if preferred_intents and form.likely_intent not in preferred_intents:
                continue
            labels.append(form.id or form.purpose.value)
    return labels[:8]


def collect_safety_notes(target_pages: list[PageRecord]) -> list[str]:
    notes: list[str] = []
    for page in target_pages[:2]:
        if page.safety.contains_destructive_actions:
            notes.append(f"{page.page_id}: contains destructive-looking actions")
        elif page.safety.contains_mutating_actions:
            notes.append(f"{page.page_id}: contains mutating-looking actions")
    return notes[:4]


def load_manifest(path: Path) -> SiteManifest:
    return SiteManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_workflow_graph(path: Path) -> WorkflowGraph | None:
    if not path.exists():
        return None
    return WorkflowGraph.model_validate_json(path.read_text(encoding="utf-8"))


def render_task_validation_markdown(summary: TaskValidationSummary) -> str:
    lines = [
        "# Task Validation",
        "",
        f"- Run: `{summary.run_dir}`",
        f"- Role: `{summary.role_profile}`",
        f"- Tasks file: `{summary.tasks_file}`",
        f"- Total tasks: `{summary.total_tasks}`",
        f"- Pass: `{summary.pass_count}`",
        f"- Partial: `{summary.partial_count}`",
        f"- Fail: `{summary.fail_count}`",
        "",
    ]
    for result in summary.results:
        lines.extend(
            [
                f"## {result.task_id}",
                f"- Status: `{result.status.value}`",
                f"- Path length: `{result.path_length}`",
                f"- Path quality: `{result.path_quality_score}`",
                f"- Next-step support: `{result.next_step_support_score}`",
                f"- Affordance support: `{result.affordance_support_score}`",
                f"- Discovered target: `{result.discovered_target}`",
            ]
        )
        if result.candidate_path_urls:
            lines.append(f"- Candidate path: `{result.candidate_path_urls}`")
        if result.key_affordances:
            lines.append(f"- Key affordances: `{result.key_affordances}`")
        if result.blockers:
            lines.append(f"- Blockers: `{result.blockers}`")
        if result.notes:
            lines.append(f"- Notes: `{result.notes}`")
        lines.append("")
    return "\n".join(lines)
