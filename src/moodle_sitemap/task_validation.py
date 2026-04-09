from __future__ import annotations

"""Task-oriented validation over saved crawl artifacts.

This module keeps the high-level validation flow readable. The lower-level
path, scoring, and affordance-selection helpers live in
`task_validation_support.py`.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json

from moodle_sitemap.models import (
    SiteManifest,
    TaskSpec,
    TaskSpecList,
    TaskValidationStatus,
    TaskValidationSummary,
    TaskValidationTaskResult,
    WorkflowGraph,
)
from moodle_sitemap.task_validation_support import (
    choose_start_page,
    collect_key_affordances,
    collect_safety_notes,
    find_best_path,
    find_cluster_supported_path,
    find_target_pages,
    load_manifest,
    load_workflow_graph,
    render_task_validation_markdown,
    score_affordance_support,
    score_best_path_confidence,
    score_first_hop_quality,
    score_key_affordance_relevance,
    score_next_step_support,
    score_path_quality,
)


@dataclass(slots=True)
class TaskValidationRunResult:
    """Paths and parsed summary produced by one task-validation run."""

    output_dir: Path
    json_path: Path
    markdown_path: Path
    summary: TaskValidationSummary


def create_task_validation_run_dir(base_dir: str | Path = "task-validation-runs") -> Path:
    """Create a timestamped output directory for task-validation artifacts."""

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
    """Load and validate the checked-in task specification JSON."""

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
    """Validate the task pack against one saved crawl or discovery run."""

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
    """Evaluate one task against a saved manifest and workflow graph."""

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
        path_edges = find_cluster_supported_path(start_page=start_page, target_pages=target_pages)
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
        result.best_path_confidence = score_best_path_confidence(path_edges)
        result.next_step_support_score = score_next_step_support(start_page, path_edges)
        result.first_hop_quality = score_first_hop_quality(start_page, path_edges)
        result.next_steps_helpful = result.next_step_support_score >= 60

    target_affordance_support = score_affordance_support(task, target_pages)
    result.affordance_support_score = target_affordance_support
    result.key_affordances = collect_key_affordances(task, target_pages)
    result.key_affordance_relevance = score_key_affordance_relevance(task, target_pages)
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
