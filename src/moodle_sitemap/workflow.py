from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from urllib.parse import urlparse

from moodle_sitemap.discover import normalize_url
from moodle_sitemap.models import (
    ActionAffordance,
    BackgroundNavigationCluster,
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
    candidate_edges: list[WorkflowEdge] = []

    for page in pages:
        for candidate in collect_edge_candidates(page):
            target_page = page_by_url.get(candidate.target_url)
            edge = build_edge(page, target_page, candidate)
            if edge is None:
                continue
            candidate_edges.append(edge)

    before_next_steps = preview_next_steps_by_page(pages, candidate_edges)
    edges, deduplicated_pairs = deduplicate_edges(candidate_edges)
    suppressed_edge_count = max(len(candidate_edges) - len(edges), 0)
    edges, background_clusters, compressed_edge_count = compress_low_value_edges(pages, edges)

    attach_background_clusters(pages, background_clusters)
    changed_pages = assign_next_steps(pages, edges, before_next_steps=before_next_steps)
    augment_next_steps_with_background_clusters(pages)

    edge_type_counts = {edge_type.value: 0 for edge_type in WorkflowEdgeType}
    edge_weight_counts = {edge_weight.value: 0 for edge_weight in EdgeWeight}
    edge_relevance_counts = {edge_relevance.value: 0 for edge_relevance in EdgeRelevance}
    pre_dedup_edge_weight_counts = {edge_weight.value: 0 for edge_weight in EdgeWeight}
    pre_dedup_edge_relevance_counts = {edge_relevance.value: 0 for edge_relevance in EdgeRelevance}
    for edge in candidate_edges:
        pre_dedup_edge_weight_counts[edge.edge_weight.value] += 1
        pre_dedup_edge_relevance_counts[edge.edge_relevance.value] += 1
    for edge in edges:
        edge_type_counts[edge.edge_type.value] += 1
        edge_weight_counts[edge.edge_weight.value] += 1
        edge_relevance_counts[edge.edge_relevance.value] += 1

    return WorkflowGraph(
        role_profile=role_profile,
        candidate_edge_count=len(candidate_edges),
        suppressed_edge_count=suppressed_edge_count,
        deduplicated_pair_count=deduplicated_pairs,
        compressed_edge_count=compressed_edge_count,
        cluster_count=len(background_clusters),
        total_edges=len(edges),
        edge_type_counts=edge_type_counts,
        edge_weight_counts=edge_weight_counts,
        edge_relevance_counts=edge_relevance_counts,
        pre_dedup_edge_weight_counts=pre_dedup_edge_weight_counts,
        pre_dedup_edge_relevance_counts=pre_dedup_edge_relevance_counts,
        next_step_changed_pages=changed_pages,
        background_clusters=background_clusters,
        edges=sorted(edges, key=lambda item: (item.from_page_id, item.target_url, item.edge_type.value)),
    )


def collect_edge_candidates(page: PageRecord) -> list[EdgeCandidate]:
    candidates: list[EdgeCandidate] = []
    explicit_targets: set[str] = set()
    seen_discovered_targets: set[str] = set()
    seen_low_value_variant_groups: set[str] = set()

    for item in page.affordances.navigation:
        if item.url:
            normalized_target = normalize_url(item.url)
            explicit_targets.add(normalized_target)
            candidates.append(
                EdgeCandidate(
                    target_url=normalized_target,
                    label=item.label,
                    kind="navigation",
                    importance=item.importance_level,
                    likely_intent=item.likely_intent,
                )
            )

    for item in page.affordances.tabs:
        if item.url:
            normalized_target = normalize_url(item.url)
            explicit_targets.add(normalized_target)
            candidates.append(
                EdgeCandidate(
                    target_url=normalized_target,
                    label=item.label,
                    kind="tab",
                    importance=ImportanceLevel.SECONDARY,
                    likely_intent=LikelyIntent.NAVIGATE,
                )
            )

    for item in page.affordances.actions:
        if item.url:
            normalized_target = normalize_url(item.url)
            explicit_targets.add(normalized_target)
            candidates.append(
                EdgeCandidate(
                    target_url=normalized_target,
                    label=item.label,
                    kind=item.element_type.value,
                    importance=item.importance_level,
                    likely_intent=item.likely_intent,
                )
            )

    for url in page.discovered_links:
        normalized_target = normalize_url(url)
        if normalized_target in explicit_targets or normalized_target in seen_discovered_targets:
            continue
        variant_group = low_value_variant_group(normalized_target)
        if variant_group and variant_group in seen_low_value_variant_groups:
            continue
        seen_discovered_targets.add(normalized_target)
        if variant_group:
            seen_low_value_variant_groups.add(variant_group)
        candidates.append(
            EdgeCandidate(
                target_url=normalized_target,
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
        target_page_type=target_page.page_type,
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

    if source_type == PageType.DASHBOARD and target_type in {
        PageType.USER_PREFERENCES,
        PageType.USER_PROFILE,
        PageType.USER_PROFILE_EDIT,
        PageType.MESSAGE_PREFERENCES,
        PageType.MESSAGES,
        PageType.PRIVATE_FILES,
        PageType.GRADEBOOK,
        PageType.REPORT_BUILDER,
        PageType.BLOG_PAGE,
        PageType.FORUM_USER_PAGE,
        PageType.CONTENT_BANK_PREFERENCES,
        PageType.USER_SETTINGS_PAGE,
    }:
        return WorkflowEdgeType.NAVIGATION, 0.78, "dashboard-secondary-surface"

    if source_type == PageType.COURSE_VIEW and target_type == PageType.ACTIVITY_VIEW:
        return WorkflowEdgeType.ACTIVITY, 0.95, "course-to-activity"

    if source_type == PageType.COURSE_VIEW and target_type == PageType.COURSE_EDIT:
        return WorkflowEdgeType.EDIT, 0.9, "course-edit-link"

    if source_type == PageType.COURSE_VIEW and target_type in {
        PageType.ADMIN_SEARCH,
        PageType.ADMIN_CATEGORY,
        PageType.ADMIN_SETTING_PAGE,
        PageType.ADMIN_TOOL_PAGE,
    }:
        return WorkflowEdgeType.SETTINGS, 0.75, "course-settings-like-link"

    if source_type == PageType.USER_PREFERENCES and target_type == PageType.MESSAGE_PREFERENCES:
        return WorkflowEdgeType.PREFERENCES, 0.95, "user-to-message-preferences"

    if source_type == PageType.MESSAGES and target_type == PageType.MESSAGE_PREFERENCES:
        return WorkflowEdgeType.PREFERENCES, 0.95, "messages-to-preferences"

    if source_type == PageType.ADMIN_SEARCH and target_type in {
        PageType.ADMIN_CATEGORY,
        PageType.ADMIN_SETTING_PAGE,
        PageType.ADMIN_TOOL_PAGE,
    }:
        return WorkflowEdgeType.ADMIN, 0.92, "admin-search-result"

    if source_type == PageType.ADMIN_CATEGORY and target_type in {
        PageType.ADMIN_SETTING_PAGE,
        PageType.ADMIN_TOOL_PAGE,
    }:
        return WorkflowEdgeType.ADMIN, 0.9, "admin-category-drilldown"

    if source_type in {
        PageType.ADMIN_SEARCH,
        PageType.ADMIN_CATEGORY,
        PageType.ADMIN_SETTING_PAGE,
        PageType.ADMIN_TOOL_PAGE,
    } and target_type in {
        PageType.ADMIN_SEARCH,
        PageType.ADMIN_CATEGORY,
        PageType.ADMIN_SETTING_PAGE,
        PageType.ADMIN_TOOL_PAGE,
    }:
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

def assign_next_steps(
    pages: list[PageRecord],
    edges: list[WorkflowEdge],
    *,
    before_next_steps: dict[str, list[str]] | None = None,
) -> list[dict[str, object]]:
    edges_by_page: dict[str, list[WorkflowEdge]] = defaultdict(list)
    for edge in edges:
        edges_by_page[edge.from_page_id].append(edge)

    changed_pages: list[dict[str, object]] = []
    for page in pages:
        ranked_edges = rank_edges_for_next_steps(page, edges_by_page.get(page.page_id, []))
        page.next_steps = [
            NextStepHint(
                page_id=edge.to_page_id,
                target_url=edge.target_url,
                target_page_type=edge.target_page_type,
                edge_type=edge.edge_type,
                edge_weight=edge.edge_weight,
                edge_relevance=edge.edge_relevance,
                label=edge.source_affordance_label,
                confidence=edge.confidence,
                likely_intent=infer_next_step_intent(edge),
                notes=edge.notes,
            )
            for edge in ranked_edges[:4]
        ]
        if before_next_steps is not None:
            previous_targets = before_next_steps.get(page.page_id, [])
            current_targets = [item.target_url for item in page.next_steps]
            if previous_targets[:4] != current_targets[:4]:
                changed_pages.append(
                    {
                        "page_id": page.page_id,
                        "before_targets": previous_targets[:4],
                        "after_targets": current_targets[:4],
                    }
                )
    return changed_pages


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
    if source_page.page_type == PageType.DASHBOARD and target_page.page_type == PageType.COURSE_VIEW:
        return EdgeWeight.HIGH, EdgeRelevance.TASK, "dashboard-course-entry"
    if source_page.page_type == PageType.DASHBOARD and target_page.page_type in {
        PageType.USER_PREFERENCES,
        PageType.USER_PROFILE,
        PageType.USER_PROFILE_EDIT,
        PageType.MESSAGE_PREFERENCES,
        PageType.MESSAGES,
        PageType.PRIVATE_FILES,
        PageType.GRADEBOOK,
        PageType.REPORT_BUILDER,
        PageType.BLOG_PAGE,
        PageType.FORUM_USER_PAGE,
        PageType.CONTENT_BANK_PREFERENCES,
        PageType.USER_SETTINGS_PAGE,
    }:
        return EdgeWeight.MEDIUM, EdgeRelevance.SUPPORT, "dashboard-secondary-surface"
    if edge_type == WorkflowEdgeType.SETTINGS:
        if candidate.importance == ImportanceLevel.PRIMARY or source_page.page_type in {
            PageType.COURSE_VIEW,
            PageType.ADMIN_SEARCH,
            PageType.ADMIN_CATEGORY,
            PageType.ADMIN_SETTING_PAGE,
            PageType.ADMIN_TOOL_PAGE,
            PageType.USER_PREFERENCES,
        }:
            return EdgeWeight.HIGH, EdgeRelevance.TASK, "settings-progression"
        return EdgeWeight.MEDIUM, EdgeRelevance.SUPPORT, "settings-support"
    if edge_type == WorkflowEdgeType.ADMIN:
        if source_page.page_type == PageType.ADMIN_SEARCH and target_page.page_type in {
            PageType.ADMIN_SETTING_PAGE,
            PageType.ADMIN_TOOL_PAGE,
        }:
            return EdgeWeight.HIGH, EdgeRelevance.TASK, "admin-search-to-specific-page"
        if source_page.page_type == PageType.ADMIN_CATEGORY and target_page.page_type in {
            PageType.ADMIN_SETTING_PAGE,
            PageType.ADMIN_TOOL_PAGE,
        }:
            return EdgeWeight.HIGH, EdgeRelevance.TASK, "admin-category-to-specific-page"
        if candidate.importance == ImportanceLevel.PRIMARY and target_page.page_type != PageType.ADMIN_CATEGORY:
            return EdgeWeight.HIGH, EdgeRelevance.TASK, "admin-primary-drilldown"
        if target_page.page_type == PageType.ADMIN_CATEGORY:
            return EdgeWeight.LOW, EdgeRelevance.NAVIGATION, "broad-admin-category"
        return EdgeWeight.MEDIUM, EdgeRelevance.SUPPORT, "admin-drilldown"
    if candidate.kind == "discovered_link":
        if "calendar/view.php" in target_page.normalized_url:
            return EdgeWeight.LOW, EdgeRelevance.CONTEXTUAL, "calendar-variant"
        if target_page.page_type in {
            PageType.ADMIN_SEARCH,
            PageType.ADMIN_CATEGORY,
            PageType.ADMIN_SETTING_PAGE,
            PageType.ADMIN_TOOL_PAGE,
        }:
            return EdgeWeight.LOW, EdgeRelevance.CONTEXTUAL, "admin-discovered-link"
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
        if source_page.page_type == PageType.ADMIN_SEARCH and target_page.page_type in {
            PageType.ADMIN_SETTING_PAGE,
            PageType.ADMIN_TOOL_PAGE,
        }:
            return EdgeWeight.HIGH, EdgeRelevance.TASK, "admin-search-navigation"
        if source_page.page_type == PageType.ADMIN_CATEGORY and target_page.page_type in {
            PageType.ADMIN_SETTING_PAGE,
            PageType.ADMIN_TOOL_PAGE,
        }:
            return EdgeWeight.HIGH, EdgeRelevance.TASK, "admin-category-navigation"
        if candidate.kind == "tab":
            return EdgeWeight.MEDIUM, EdgeRelevance.SUPPORT, "tab-navigation"
        if source_page.page_type in {
            PageType.ADMIN_SEARCH,
            PageType.ADMIN_CATEGORY,
            PageType.ADMIN_SETTING_PAGE,
            PageType.ADMIN_TOOL_PAGE,
        } and target_page.page_type in {
            PageType.ADMIN_SEARCH,
            PageType.ADMIN_CATEGORY,
            PageType.ADMIN_SETTING_PAGE,
            PageType.ADMIN_TOOL_PAGE,
        }:
            return EdgeWeight.LOW, EdgeRelevance.NAVIGATION, "generic-admin-navigation"
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
        if edge.edge_type == WorkflowEdgeType.RELATED and edge.reason_hint == "reporting-surface":
            return LikelyIntent.REPORT
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
    primary_intent = page.primary_page_intent
    if primary_intent == LikelyIntent.UNKNOWN:
        return 1
    if infer_next_step_intent(edge) == primary_intent:
        return 0
    return 1


def deduplicate_edges(candidate_edges: list[WorkflowEdge]) -> tuple[list[WorkflowEdge], int]:
    edge_map: dict[tuple[str, str], WorkflowEdge] = {}
    pair_counts: Counter[tuple[str, str]] = Counter()
    for edge in candidate_edges:
        key = (edge.from_page_id, edge.target_url)
        pair_counts[key] += 1
        current = edge_map.get(key)
        if current is None or edge_preference(edge) > edge_preference(current):
            edge_map[key] = edge
    deduplicated_pairs = sum(1 for count in pair_counts.values() if count > 1)
    return list(edge_map.values()), deduplicated_pairs


def preview_next_steps_by_page(pages: list[PageRecord], edges: list[WorkflowEdge]) -> dict[str, list[str]]:
    edges_by_page: dict[str, list[WorkflowEdge]] = defaultdict(list)
    for edge in edges:
        edges_by_page[edge.from_page_id].append(edge)
    return {
        page.page_id: [edge.target_url for edge in rank_edges_for_next_steps(page, edges_by_page.get(page.page_id, []))[:4]]
        for page in pages
    }


def rank_edges_for_next_steps(page: PageRecord, edges: list[WorkflowEdge]) -> list[WorkflowEdge]:
    candidates = sorted(
        edges,
        key=lambda edge: (
            edge_sort_rank(edge.edge_weight),
            edge_relevance_rank(edge.edge_relevance),
            source_importance_rank(edge.source_affordance_importance),
            intent_alignment_rank(page, edge),
            -(edge.confidence or 0.0),
            edge.target_url,
        ),
    )
    if any(edge.edge_relevance in {EdgeRelevance.TASK, EdgeRelevance.SUPPORT} for edge in candidates):
        candidates = [edge for edge in candidates if edge.edge_relevance != EdgeRelevance.CONTEXTUAL]
    if page.primary_page_intent != LikelyIntent.UNKNOWN:
        aligned = [edge for edge in candidates if infer_next_step_intent(edge) == page.primary_page_intent]
        if aligned:
            non_aligned = [edge for edge in candidates if infer_next_step_intent(edge) != page.primary_page_intent]
            candidates = aligned + non_aligned
    if page.page_type == PageType.DASHBOARD:
        candidates = rebalance_dashboard_next_steps(candidates)
    return candidates


def rebalance_dashboard_next_steps(edges: list[WorkflowEdge]) -> list[WorkflowEdge]:
    if not edges:
        return edges

    selected: list[WorkflowEdge] = []
    seen_target_types: set[PageType | None] = set()

    for edge in edges:
        if edge.edge_relevance == EdgeRelevance.TASK:
            selected.append(edge)
            seen_target_types.add(edge.target_page_type)
            break

    preferred_types = [
        PageType.USER_PREFERENCES,
        PageType.USER_PROFILE,
        PageType.MESSAGE_PREFERENCES,
        PageType.CALENDAR,
        PageType.GRADEBOOK,
        PageType.PRIVATE_FILES,
        PageType.BLOG_PAGE,
        PageType.FORUM_USER_PAGE,
    ]
    for preferred in preferred_types:
        if len(selected) >= 4:
            break
        for edge in edges:
            if edge in selected:
                continue
            if edge.target_page_type != preferred:
                continue
            if edge.target_page_type in seen_target_types:
                continue
            selected.append(edge)
            seen_target_types.add(edge.target_page_type)
            break

    for edge in edges:
        if len(selected) >= 4:
            break
        if edge in selected:
            continue
        selected.append(edge)

    return selected


def low_value_variant_group(url: str) -> str | None:
    path = urlparse(url).path
    if path == "/calendar/view.php":
        return "/calendar/view.php"
    return None


def compress_low_value_edges(
    pages: list[PageRecord],
    edges: list[WorkflowEdge],
) -> tuple[list[WorkflowEdge], list[BackgroundNavigationCluster], int]:
    page_by_id = {page.page_id: page for page in pages}
    compressed_edges: list[WorkflowEdge] = []
    background_clusters: list[BackgroundNavigationCluster] = []
    compressed_edge_count = 0
    grouped: dict[tuple[str, str], list[WorkflowEdge]] = defaultdict(list)

    for edge in edges:
        family = compressible_family_for_edge(page_by_id.get(edge.from_page_id), edge)
        if family is None:
            compressed_edges.append(edge)
            continue
        grouped[(edge.from_page_id, family)].append(edge)

    for (source_page_id, family_key), family_edges in grouped.items():
        source_page = page_by_id.get(source_page_id)
        if source_page is None:
            compressed_edges.extend(family_edges)
            continue
        if not should_compress_family(source_page, family_key, family_edges):
            compressed_edges.extend(family_edges)
            continue
        background_clusters.append(
            BackgroundNavigationCluster(
                cluster_type=cluster_type_for_family(family_key),
                source_page_id=source_page_id,
                family_key=family_key,
                count=len(family_edges),
                representative_targets=[edge.target_url for edge in family_edges[:3]],
                edge_relevance=EdgeRelevance.CONTEXTUAL,
                edge_weight=EdgeWeight.LOW,
                reason_hint=reason_hint_for_family(family_key),
            )
        )
        compressed_edge_count += len(family_edges)

    return (
        sorted(compressed_edges, key=lambda item: (item.from_page_id, item.target_url, item.edge_type.value)),
        sorted(background_clusters, key=lambda item: (item.source_page_id, item.family_key)),
        compressed_edge_count,
    )


def compressible_family_for_edge(source_page: PageRecord | None, edge: WorkflowEdge) -> str | None:
    if edge.edge_weight != EdgeWeight.LOW:
        return None
    if edge.edge_relevance not in {EdgeRelevance.NAVIGATION, EdgeRelevance.CONTEXTUAL}:
        return None
    path = urlparse(edge.target_url).path
    if path == "/calendar/view.php":
        return "/calendar/view.php"
    if path == "/calendar/managesubscriptions.php":
        return "/calendar/managesubscriptions.php"
    if path.startswith("/admin/tool/"):
        return "/admin/tool"
    if path == "/admin/settings.php":
        return "/admin/settings.php"
    if path == "/admin/category.php":
        return "/admin/category.php"
    if path == "/admin/index.php":
        return "/admin/index.php"
    if path == "/admin/search.php":
        return "/admin/search.php"
    if source_page and source_page.page_type in {
        PageType.ADMIN_SEARCH,
        PageType.ADMIN_CATEGORY,
        PageType.ADMIN_SETTING_PAGE,
        PageType.ADMIN_TOOL_PAGE,
    } and path.startswith("/admin/"):
        return "/admin/background"
    return None


def should_compress_family(
    source_page: PageRecord,
    family_key: str,
    family_edges: list[WorkflowEdge],
) -> bool:
    if family_key.startswith("/calendar/"):
        return len(family_edges) >= 1
    if family_key.startswith("/admin/"):
        if source_page.page_type in {
            PageType.ADMIN_SEARCH,
            PageType.ADMIN_CATEGORY,
            PageType.ADMIN_SETTING_PAGE,
            PageType.ADMIN_TOOL_PAGE,
        }:
            return len(family_edges) >= 1
        return len(family_edges) >= 2
    return len(family_edges) >= 2


def cluster_type_for_family(family_key: str) -> str:
    if family_key.startswith("/calendar/"):
        return "repeated_variant_cluster"
    if family_key.startswith("/admin/"):
        return "generic_admin_navigation_cluster"
    return "route_family_cluster"


def reason_hint_for_family(family_key: str) -> str:
    if family_key.startswith("/calendar/"):
        return "compressed-calendar-variants"
    if family_key.startswith("/admin/"):
        return "compressed-admin-background-navigation"
    return "compressed-low-value-navigation"


def attach_background_clusters(
    pages: list[PageRecord],
    background_clusters: list[BackgroundNavigationCluster],
) -> None:
    clusters_by_page: dict[str, list[BackgroundNavigationCluster]] = defaultdict(list)
    for cluster in background_clusters:
        clusters_by_page[cluster.source_page_id].append(cluster)
    for page in pages:
        page.background_navigation_clusters = clusters_by_page.get(page.page_id, [])


def augment_next_steps_with_background_clusters(pages: list[PageRecord]) -> None:
    page_by_url = {page.normalized_url: page for page in pages}
    for page in pages:
        if page.page_type != PageType.DASHBOARD:
            continue
        if len(page.next_steps) >= 4:
            continue
        existing_targets = {step.target_url for step in page.next_steps}
        for cluster in page.background_navigation_clusters:
            if len(page.next_steps) >= 4:
                break
            if cluster.family_key not in {"/calendar/view.php", "/calendar/managesubscriptions.php"}:
                continue
            for target_url in cluster.representative_targets:
                target_page = page_by_url.get(target_url)
                if target_page is None or target_page.normalized_url in existing_targets:
                    continue
                page.next_steps.append(
                    NextStepHint(
                        page_id=target_page.page_id,
                        target_url=target_page.normalized_url,
                        target_page_type=target_page.page_type,
                        edge_type=WorkflowEdgeType.NAVIGATION,
                        edge_weight=EdgeWeight.LOW,
                        edge_relevance=EdgeRelevance.SUPPORT,
                        label="Calendar",
                        confidence=0.45,
                        likely_intent=LikelyIntent.NAVIGATE,
                        notes="background-cluster-first-hop",
                    )
                )
                existing_targets.add(target_page.normalized_url)
                break
