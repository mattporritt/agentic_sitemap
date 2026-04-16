# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

"""Helper logic for task-oriented validation over saved artifacts."""

from collections import defaultdict, deque
from pathlib import Path

from moodle_sitemap.models import (
    EdgeRelevance,
    EdgeWeight,
    ImportanceLevel,
    LikelyIntent,
    PageRecord,
    PageType,
    SiteManifest,
    TaskSpec,
    TaskValidationSummary,
    WorkflowEdge,
    WorkflowEdgeType,
    WorkflowGraph,
)


def choose_start_page(task: TaskSpec, pages: list[PageRecord]) -> PageRecord | None:
    """Pick the starting page for a task from the saved run."""

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
    """Return pages matching the task's target constraints."""

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
    """Group a URL into a path family for task matching."""

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
    """Find the best saved-graph path from the start page to any target."""

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


def find_cluster_supported_path(
    *,
    start_page: PageRecord,
    target_pages: list[PageRecord],
) -> list[WorkflowEdge] | None:
    """Recover a weak one-hop path from compressed background navigation."""

    target_by_url = {page.normalized_url: page for page in target_pages}
    for cluster in start_page.background_navigation_clusters:
        for target_url in cluster.representative_targets:
            target_page = target_by_url.get(target_url)
            if target_page is None:
                continue
            return [
                WorkflowEdge(
                    from_page_id=start_page.page_id,
                    to_page_id=target_page.page_id,
                    target_url=target_page.normalized_url,
                    target_page_type=target_page.page_type,
                    edge_type=WorkflowEdgeType.NAVIGATION,
                    edge_weight=EdgeWeight.LOW,
                    edge_relevance=EdgeRelevance.SUPPORT,
                    source_affordance_label="Calendar",
                    source_affordance_kind="background_cluster",
                    confidence=0.45,
                    reason_hint="background-cluster-first-hop",
                    notes="background-cluster-first-hop",
                )
            ]
    return None


def edge_sort_key(edge: WorkflowEdge) -> tuple[int, int, float]:
    """Sort paths toward stronger, clearer edges first."""

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
    """Score how clear a path looks from saved edge metadata."""

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
    """Score whether the start page's `next_steps` help with the first hop."""

    if not path_edges:
        return 100
    first_edge = path_edges[0]
    labels = {step.label for step in start_page.next_steps if step.label}
    urls = {step.target_url for step in start_page.next_steps}
    page_ids = {step.page_id for step in start_page.next_steps if step.page_id}
    target_types = {step.target_page_type for step in start_page.next_steps if step.target_page_type}
    if first_edge.target_url in urls:
        return 100
    if first_edge.to_page_id and first_edge.to_page_id in page_ids:
        return 95
    if first_edge.target_page_type and first_edge.target_page_type in target_types:
        return 80
    if first_edge.source_affordance_label and first_edge.source_affordance_label in labels:
        return 85
    return 20


def score_first_hop_quality(start_page: PageRecord, path_edges: list[WorkflowEdge]) -> int:
    """Combine next-step support with the strength of the first edge."""

    if not path_edges:
        return 0
    first_edge = path_edges[0]
    score = score_next_step_support(start_page, path_edges)
    score += {
        EdgeRelevance.TASK: 20,
        EdgeRelevance.SUPPORT: 12,
        EdgeRelevance.NAVIGATION: 6,
        EdgeRelevance.CONTEXTUAL: 0,
    }[first_edge.edge_relevance]
    score += {
        EdgeWeight.HIGH: 10,
        EdgeWeight.MEDIUM: 6,
        EdgeWeight.LOW: 0,
    }[first_edge.edge_weight]
    return min(100, score)


def score_best_path_confidence(path_edges: list[WorkflowEdge]) -> int:
    """Average edge confidence across the candidate path."""

    if not path_edges:
        return 0
    average = sum(edge.confidence or 0.0 for edge in path_edges) / len(path_edges)
    return round(average * 100)


def score_affordance_support(task: TaskSpec, target_pages: list[PageRecord]) -> int:
    """Score whether the target pages expose the required affordance intents."""

    if not target_pages:
        return 0
    if not task.required_affordance_intents:
        return 70
    intents = set(task.required_affordance_intents)
    best = 0
    for page in target_pages:
        page_intents = {action.likely_intent for action in page.affordances.actions} | {
            form.likely_intent for form in page.affordances.forms
        } | {nav.likely_intent for nav in page.affordances.navigation}
        overlap = len(intents & page_intents)
        if overlap:
            best = max(best, min(100, 40 + overlap * 30))
    return best


def collect_key_affordances(task: TaskSpec, target_pages: list[PageRecord]) -> list[str]:
    """Return task-relevant affordance labels for the matched target pages."""

    ranked = rank_task_affordances(task, target_pages)
    labels: list[str] = []
    for _, label in ranked:
        if label not in labels:
            labels.append(label)
        if len(labels) >= 8:
            break
    return labels


def score_key_affordance_relevance(task: TaskSpec, target_pages: list[PageRecord]) -> int:
    """Score how relevant the top extracted affordances look for the task."""

    ranked = rank_task_affordances(task, target_pages)
    if not ranked:
        return 0
    top_scores = [score for score, _ in ranked[:3]]
    return min(100, round(sum(top_scores) / len(top_scores)))


def rank_task_affordances(task: TaskSpec, target_pages: list[PageRecord]) -> list[tuple[int, str]]:
    """Rank visible controls by task relevance instead of raw page order."""

    preferred_intents = set(task.required_affordance_intents)
    ranked: list[tuple[int, str]] = []
    for page in target_pages[:3]:
        for action in page.affordances.actions:
            if is_generic_affordance_label(action.label):
                continue
            ranked.append(
                (
                    score_action_affordance(
                        task,
                        page,
                        action.label,
                        action.likely_intent,
                        action.importance_level,
                        action.prominence_score,
                    ),
                    action.label,
                )
            )
        for form in page.affordances.forms:
            label = most_relevant_form_label(form)
            if is_generic_affordance_label(label):
                continue
            score = 35
            if preferred_intents and form.likely_intent in preferred_intents:
                score += 35
            if form.likely_intent == page.primary_page_intent:
                score += 20
            score += {
                ImportanceLevel.PRIMARY: 10,
                ImportanceLevel.SECONDARY: 6,
                ImportanceLevel.TERTIARY: 2,
            }[form.importance_level]
            ranked.append((score, label))
        for nav in page.affordances.navigation:
            if is_generic_affordance_label(nav.label):
                continue
            score = 20
            if preferred_intents and nav.likely_intent in preferred_intents:
                score += 25
            if nav.likely_intent == page.primary_page_intent:
                score += 15
            score += {
                ImportanceLevel.PRIMARY: 12,
                ImportanceLevel.SECONDARY: 6,
                ImportanceLevel.TERTIARY: 2,
            }[nav.importance_level]
            ranked.append((score, nav.label))
    return sorted(ranked, key=lambda item: (-item[0], item[1].lower()))


def score_action_affordance(
    task: TaskSpec,
    page: PageRecord,
    label: str,
    intent: LikelyIntent,
    importance: ImportanceLevel,
    prominence_score: int,
) -> int:
    """Score one action label for task relevance."""

    preferred_intents = set(task.required_affordance_intents)
    score = 20 + min(prominence_score, 40)
    if preferred_intents and intent in preferred_intents:
        score += 30
    if intent == page.primary_page_intent:
        score += 20
    if keyword_alignment(task, label):
        score += 20
    score += {
        ImportanceLevel.PRIMARY: 12,
        ImportanceLevel.SECONDARY: 6,
        ImportanceLevel.TERTIARY: 2,
    }[importance]
    return score


def keyword_alignment(task: TaskSpec, label: str) -> bool:
    """Check whether a label matches task-language keywords."""

    lowered = label.lower()
    keywords = [
        "profile",
        "preference",
        "notification",
        "message",
        "calendar",
        "grade",
        "blog",
        "forum",
        "private files",
        "ai",
        "registration",
        "course",
        "edit",
        "setting",
    ]
    return any(word in lowered and word in task.success_hint.lower() for word in keywords)


def most_relevant_form_label(form) -> str:
    """Choose the most useful label for a form in task reports."""

    for submit in form.submit_controls:
        if submit.label and not is_generic_affordance_label(submit.label):
            return submit.label
    if form.id:
        return form.id
    return form.purpose.value


def is_generic_affordance_label(label: str | None) -> bool:
    """Filter out broad UI chrome that is rarely task-relevant."""

    if not label:
        return True
    lowered = label.strip().lower()
    generic = {
        "skip to main content",
        "moodle demo",
        "dashboard",
        "message",
        "got it",
        "collapse",
        "open block drawer",
        "tt",
        "st",
        "au",
    }
    return (
        lowered in generic
        or lowered.startswith("0 there are ")
        or lowered.startswith("skip ")
    )


def collect_safety_notes(target_pages: list[PageRecord]) -> list[str]:
    """Return concise safety notes for the target pages."""

    notes: list[str] = []
    for page in target_pages[:2]:
        if page.safety.contains_destructive_actions:
            notes.append(f"{page.page_id}: contains destructive-looking actions")
        elif page.safety.contains_mutating_actions:
            notes.append(f"{page.page_id}: contains mutating-looking actions")
    return notes[:4]


def load_manifest(path: Path) -> SiteManifest:
    """Load a saved sitemap manifest."""

    return SiteManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_workflow_graph(path: Path) -> WorkflowGraph | None:
    """Load a saved workflow graph if one exists."""

    if not path.exists():
        return None
    return WorkflowGraph.model_validate_json(path.read_text(encoding="utf-8"))


def render_task_validation_markdown(summary: TaskValidationSummary) -> str:
    """Render a concise human-readable task-validation summary."""

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
                f"- Best path confidence: `{result.best_path_confidence}`",
                f"- First-hop quality: `{result.first_hop_quality}`",
                f"- Next-step support: `{result.next_step_support_score}`",
                f"- Affordance support: `{result.affordance_support_score}`",
                f"- Key-affordance relevance: `{result.key_affordance_relevance}`",
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
