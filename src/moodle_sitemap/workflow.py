from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from urllib.parse import urlparse

from moodle_sitemap.discover import normalize_url
from moodle_sitemap.models import (
    ActionAffordance,
    EdgeRelevance,
    EdgeWeight,
    ImportanceLevel,
    LikelyIntent,
    NavigationItem,
    NextStepHint,
    PageRecord,
    PageType,
    TabAffordance,
    WorkflowEdge,
    WorkflowEdgeType,
    WorkflowGraph,
)


@dataclass(frozen=True)
class EdgeCandidate:
    target_url: str
    label: str | None
    kind: str
    importance: ImportanceLevel | None = None
    likely_intent: LikelyIntent = LikelyIntent.UNKNOWN


def derive_workflow_graph(pages: list[PageRecord], *, role_profile: str = "unlabeled") -> WorkflowGraph:
    page_by_url = {page.normalized_url: page for page in pages}
    edge_map: dict[tuple[str, str, str], WorkflowEdge] = {}

    for page in pages:
        for candidate in collect_edge_candidates(page):
            target_page = page_by_url.get(candidate.target_url)
            edge = build_edge(page, target_page, candidate)
            if edge is None:
                continue
            key = (edge.from_page_id, edge.target_url, edge.edge_type.value)
            current = edge_map.get(key)
            if current is None or edge_preference(edge) > edge_preference(current):
                edge_map[key] = edge

    edges = list(edge_map.values())

    assign_next_steps(pages, edges)

    edge_type_counts = {edge_type.value: 0 for edge_type in WorkflowEdgeType}
    edge_weight_counts = {edge_weight.value: 0 for edge_weight in EdgeWeight}
    edge_relevance_counts = {edge_relevance.value: 0 for edge_relevance in EdgeRelevance}
    for edge in edges:
        edge_type_counts[edge.edge_type.value] += 1
        edge_weight_counts[edge.edge_weight.value] += 1
        edge_relevance_counts[edge.edge_relevance.value] += 1

    return WorkflowGraph(
        role_profile=role_profile,
        total_edges=len(edges),
        edge_type_counts=edge_type_counts,
        edge_weight_counts=edge_weight_counts,
        edge_relevance_counts=edge_relevance_counts,
        edges=sorted(edges, key=lambda item: (item.from_page_id, item.target_url, item.edge_type.value)),
    )


def collect_edge_candidates(page: PageRecord) -> list[EdgeCandidate]:
    candidates: list[EdgeCandidate] = []

    for item in page.affordances.navigation:
        if item.url:
            candidates.append(
                EdgeCandidate(
                    target_url=normalize_url(item.url),
                    label=item.label,
                    kind="navigation",
                    importance=item.importance_level,
                    likely_intent=item.likely_intent,
                )
            )

    for item in page.affordances.tabs:
        if item.url:
            candidates.append(
                EdgeCandidate(
                    target_url=normalize_url(item.url),
                    label=item.label,
                    kind="tab",
                    importance=ImportanceLevel.SECONDARY,
                    likely_intent=LikelyIntent.NAVIGATE,
                )
            )

    for item in page.affordances.actions:
        if item.url:
            candidates.append(
                EdgeCandidate(
                    target_url=normalize_url(item.url),
                    label=item.label,
                    kind=item.element_type.value,
                    importance=item.importance_level,
                    likely_intent=item.likely_intent,
                )
            )

    for url in page.discovered_links:
        candidates.append(
            EdgeCandidate(
                target_url=normalize_url(url),
                label=None,
                kind="discovered_link",
                importance=ImportanceLevel.TERTIARY,
                likely_intent=LikelyIntent.UNKNOWN,
            )
        )

    return candidates


def build_edge(
    source_page: PageRecord,
    target_page: PageRecord | None,
    candidate: EdgeCandidate,
) -> WorkflowEdge | None:
    if target_page is None:
        return None
    if target_page.page_id == source_page.page_id:
        return None

    edge_type, confidence, notes = infer_edge_type(source_page, target_page, candidate)
    edge_weight, edge_relevance, reason_hint = infer_edge_weight(
        source_page=source_page,
        target_page=target_page,
        candidate=candidate,
        edge_type=edge_type,
    )
    return WorkflowEdge(
        from_page_id=source_page.page_id,
        to_page_id=target_page.page_id,
        target_url=target_page.normalized_url,
        edge_type=edge_type,
        source_affordance_label=candidate.label,
        source_affordance_kind=candidate.kind,
        source_affordance_importance=candidate.importance,
        edge_weight=edge_weight,
        edge_relevance=edge_relevance,
        confidence=confidence,
        reason_hint=reason_hint,
        notes=notes,
    )


def infer_edge_type(
    source_page: PageRecord,
    target_page: PageRecord,
    candidate: EdgeCandidate,
) -> tuple[WorkflowEdgeType, float, str | None]:
    source_type = source_page.page_type
    target_type = target_page.page_type
    label = (candidate.label or "").lower()
    kind = candidate.kind

    if source_type == PageType.DASHBOARD and target_type == PageType.COURSE_VIEW:
        return WorkflowEdgeType.NAVIGATION, 0.95, "dashboard-to-course"

    if source_type == PageType.COURSE_VIEW and target_type == PageType.ACTIVITY_VIEW:
        return WorkflowEdgeType.ACTIVITY, 0.95, "course-to-activity"

    if source_type == PageType.COURSE_VIEW and target_type == PageType.COURSE_EDIT:
        return WorkflowEdgeType.EDIT, 0.9, "course-edit-link"

    if source_type == PageType.COURSE_VIEW and target_type == PageType.ADMIN_SETTINGS:
        return WorkflowEdgeType.SETTINGS, 0.75, "course-settings-like-link"

    if source_type == PageType.USER_PREFERENCES and target_type == PageType.MESSAGE_PREFERENCES:
        return WorkflowEdgeType.PREFERENCES, 0.95, "user-to-message-preferences"

    if source_type == PageType.MESSAGES and target_type == PageType.MESSAGE_PREFERENCES:
        return WorkflowEdgeType.PREFERENCES, 0.95, "messages-to-preferences"

    if source_type == PageType.ADMIN_SETTINGS and target_type == PageType.ADMIN_SETTINGS:
        return WorkflowEdgeType.ADMIN, 0.85, "admin-to-admin-navigation"

    if kind == "tab":
        return WorkflowEdgeType.NAVIGATION, 0.8, "tab-navigation"

    if kind == "navigation":
        return WorkflowEdgeType.NAVIGATION, 0.8, "navigation-link"

    if "edit" in label:
        return WorkflowEdgeType.EDIT, 0.8, "edit-labelled-link"

    if "setting" in label or "preferences" in label:
        if "preference" in label:
            return WorkflowEdgeType.PREFERENCES, 0.8, "preferences-labelled-link"
        return WorkflowEdgeType.SETTINGS, 0.8, "settings-labelled-link"

    if is_parent_child_edge(source_page, target_page):
        return WorkflowEdgeType.PARENT_CHILD, 0.7, "breadcrumb-or-depth-parent"

    return WorkflowEdgeType.RELATED, 0.55, None


def is_parent_child_edge(source_page: PageRecord, target_page: PageRecord) -> bool:
    if target_page.crawl_depth >= source_page.crawl_depth:
        return False
    if not source_page.breadcrumbs:
        return False

    target_title = (target_page.title or "").lower()
    breadcrumb_text = " / ".join(item.lower() for item in source_page.breadcrumbs)
    source_path = urlparse(source_page.normalized_url).path
    target_path = urlparse(target_page.normalized_url).path

    if target_title and target_title in breadcrumb_text:
        return True
    if target_path != "/" and source_path.startswith(target_path):
        return True
    return False


def assign_next_steps(pages: list[PageRecord], edges: list[WorkflowEdge]) -> None:
    edges_by_page: dict[str, list[WorkflowEdge]] = defaultdict(list)
    for edge in edges:
        edges_by_page[edge.from_page_id].append(edge)

    for page in pages:
        candidates = sorted(
            edges_by_page.get(page.page_id, []),
            key=lambda edge: (
                edge_sort_rank(edge.edge_weight),
                edge_relevance_rank(edge.edge_relevance),
                source_importance_rank(edge.source_affordance_importance),
                intent_alignment_rank(page, edge),
                -(edge.confidence or 0.0),
                edge.target_url,
            ),
        )
        page.next_steps = [
            NextStepHint(
                page_id=edge.to_page_id,
                target_url=edge.target_url,
                edge_type=edge.edge_type,
                edge_weight=edge.edge_weight,
                edge_relevance=edge.edge_relevance,
                label=edge.source_affordance_label,
                confidence=edge.confidence,
                likely_intent=infer_next_step_intent(edge),
                notes=edge.notes,
            )
            for edge in candidates[:5]
        ]


def edge_preference(edge: WorkflowEdge) -> tuple[float, int, int]:
    kind_rank = {
        "navigation": 4,
        "tab": 4,
        "link": 3,
        "submit": 3,
        "button": 2,
        "menu_trigger": 2,
        "discovered_link": 1,
    }
    return (
        -edge_sort_rank(edge.edge_weight),
        -edge_relevance_rank(edge.edge_relevance),
        edge.confidence or 0.0,
        importance_rank(edge.source_affordance_importance),
        kind_rank.get(edge.source_affordance_kind or "", 0),
        1 if edge.source_affordance_label else 0,
    )


def infer_edge_weight(
    *,
    source_page: PageRecord,
    target_page: PageRecord,
    candidate: EdgeCandidate,
    edge_type: WorkflowEdgeType,
) -> tuple[EdgeWeight, EdgeRelevance, str]:
    if edge_type in {WorkflowEdgeType.PREFERENCES, WorkflowEdgeType.EDIT, WorkflowEdgeType.ACTIVITY}:
        return EdgeWeight.HIGH, EdgeRelevance.TASK, f"{edge_type.value}-workflow"
    if edge_type == WorkflowEdgeType.SETTINGS:
        if candidate.importance == ImportanceLevel.PRIMARY or source_page.page_type in {
            PageType.COURSE_VIEW,
            PageType.ADMIN_SETTINGS,
            PageType.USER_PREFERENCES,
        }:
            return EdgeWeight.HIGH, EdgeRelevance.TASK, "settings-progression"
        return EdgeWeight.MEDIUM, EdgeRelevance.SUPPORT, "settings-support"
    if edge_type == WorkflowEdgeType.ADMIN:
        if candidate.importance == ImportanceLevel.PRIMARY:
            return EdgeWeight.HIGH, EdgeRelevance.TASK, "admin-primary-drilldown"
        return EdgeWeight.MEDIUM, EdgeRelevance.SUPPORT, "admin-drilldown"
    if candidate.kind == "discovered_link":
        if "calendar/view.php" in target_page.normalized_url:
            return EdgeWeight.LOW, EdgeRelevance.CONTEXTUAL, "calendar-variant"
        return EdgeWeight.LOW, EdgeRelevance.CONTEXTUAL, "discovered-link"
    if candidate.likely_intent in {
        LikelyIntent.CREATE,
        LikelyIntent.EDIT,
        LikelyIntent.SAVE,
        LikelyIntent.CONFIGURE,
        LikelyIntent.MESSAGE,
        LikelyIntent.UPLOAD,
    }:
        if candidate.importance == ImportanceLevel.PRIMARY:
            return EdgeWeight.HIGH, EdgeRelevance.TASK, "primary-intent-bearing-action"
        return EdgeWeight.MEDIUM, EdgeRelevance.SUPPORT, "intent-bearing-action"
    if edge_type == WorkflowEdgeType.NAVIGATION:
        if source_page.page_type == PageType.DASHBOARD and target_page.page_type == PageType.COURSE_VIEW:
            return EdgeWeight.HIGH, EdgeRelevance.TASK, "dashboard-course-entry"
        if candidate.kind == "tab":
            return EdgeWeight.MEDIUM, EdgeRelevance.SUPPORT, "tab-navigation"
        if candidate.importance == ImportanceLevel.PRIMARY:
            return EdgeWeight.MEDIUM, EdgeRelevance.SUPPORT, "primary-navigation"
        return EdgeWeight.LOW, EdgeRelevance.NAVIGATION, "generic-navigation"
    if edge_type == WorkflowEdgeType.PARENT_CHILD:
        return EdgeWeight.LOW, EdgeRelevance.NAVIGATION, "breadcrumb-parent"
    return EdgeWeight.LOW, EdgeRelevance.CONTEXTUAL, "fallback-related"


def infer_next_step_intent(edge: WorkflowEdge) -> LikelyIntent:
    if edge.edge_relevance == EdgeRelevance.TASK:
        if edge.edge_type == WorkflowEdgeType.ACTIVITY:
            return LikelyIntent.VIEW
        if edge.edge_type == WorkflowEdgeType.EDIT:
            return LikelyIntent.EDIT
        if edge.edge_type in {
            WorkflowEdgeType.SETTINGS,
            WorkflowEdgeType.PREFERENCES,
            WorkflowEdgeType.ADMIN,
        }:
            return LikelyIntent.CONFIGURE
    if edge.edge_type == WorkflowEdgeType.PREFERENCES:
        return LikelyIntent.CONFIGURE
    if edge.edge_type == WorkflowEdgeType.EDIT:
        return LikelyIntent.EDIT
    if edge.edge_type == WorkflowEdgeType.SETTINGS:
        return LikelyIntent.CONFIGURE
    if edge.edge_type == WorkflowEdgeType.ACTIVITY:
        return LikelyIntent.VIEW
    if edge.edge_type == WorkflowEdgeType.NAVIGATION:
        return LikelyIntent.NAVIGATE
    return LikelyIntent.UNKNOWN


def edge_sort_rank(weight: EdgeWeight) -> int:
    return {EdgeWeight.HIGH: 0, EdgeWeight.MEDIUM: 1, EdgeWeight.LOW: 2}[weight]


def edge_relevance_rank(relevance: EdgeRelevance) -> int:
    return {
        EdgeRelevance.TASK: 0,
        EdgeRelevance.SUPPORT: 1,
        EdgeRelevance.NAVIGATION: 2,
        EdgeRelevance.CONTEXTUAL: 3,
    }[relevance]


def importance_rank(value: ImportanceLevel | None) -> int:
    if value is None:
        return 0
    return {
        ImportanceLevel.PRIMARY: 3,
        ImportanceLevel.SECONDARY: 2,
        ImportanceLevel.TERTIARY: 1,
    }[value]


def source_importance_rank(value: ImportanceLevel | None) -> int:
    if value is None:
        return 3
    return {
        ImportanceLevel.PRIMARY: 0,
        ImportanceLevel.SECONDARY: 1,
        ImportanceLevel.TERTIARY: 2,
    }[value]


def intent_alignment_rank(page: PageRecord, edge: WorkflowEdge) -> int:
    primary_intent = page.task_summary.primary_page_intent
    if primary_intent == LikelyIntent.UNKNOWN:
        return 1
    if infer_next_step_intent(edge) == primary_intent:
        return 0
    return 1
