# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from moodle_sitemap.models import (
    ActionAffordance,
    AffordanceElementType,
    EdgeRelevance,
    EdgeWeight,
    ImportanceLevel,
    LikelyIntent,
    NavigationItem,
    NextStepHint,
    PageAffordances,
    PageRecord,
    PageTaskSummary,
    PageType,
    TabAffordance,
    WorkflowEdgeType,
)
from moodle_sitemap.workflow import derive_workflow_graph


def make_page(
    page_id: str,
    url: str,
    *,
    page_type: PageType,
    actions: list[ActionAffordance] | None = None,
    navigation: list[NavigationItem] | None = None,
    tabs: list[TabAffordance] | None = None,
    breadcrumbs: list[str] | None = None,
    crawl_depth: int = 0,
    title: str | None = None,
    task_summary: PageTaskSummary | None = None,
) -> PageRecord:
    return PageRecord(
        page_id=page_id,
        url=url,
        normalized_url=url,
        final_url=url,
        title=title or page_id,
        page_type=page_type,
        body_classes=[],
        breadcrumbs=breadcrumbs or [],
        affordances=PageAffordances(
            actions=actions or [],
            navigation=navigation or [],
            tabs=tabs or [],
        ),
        task_summary=task_summary or PageTaskSummary(),
        discovered_links=[],
        network=[],
        crawl_depth=crawl_depth,
    )


def test_derive_workflow_graph_links_dashboard_to_course_navigation() -> None:
    dashboard = make_page(
        "0001-my",
        "https://example.com/my",
        page_type=PageType.DASHBOARD,
        navigation=[
            NavigationItem(label="Course 1", url="https://example.com/course/view.php?id=4", current=False)
        ],
    )
    course = make_page(
        "0002-course",
        "https://example.com/course/view.php?id=4",
        page_type=PageType.COURSE_VIEW,
    )

    graph = derive_workflow_graph([dashboard, course])

    assert graph.total_edges == 1
    assert graph.edges[0].edge_type == WorkflowEdgeType.NAVIGATION
    assert graph.edges[0].edge_weight == EdgeWeight.HIGH
    assert graph.edges[0].edge_relevance == EdgeRelevance.TASK
    assert graph.edges[0].to_page_id == "0002-course"
    assert dashboard.next_steps[0] == NextStepHint(
        page_id="0002-course",
        target_url="https://example.com/course/view.php?id=4",
        target_page_type=PageType.COURSE_VIEW,
        edge_type=WorkflowEdgeType.NAVIGATION,
        edge_weight=EdgeWeight.HIGH,
        edge_relevance=EdgeRelevance.TASK,
        label="Course 1",
        confidence=0.95,
        likely_intent=LikelyIntent.NAVIGATE,
        notes="dashboard-to-course",
    )


def test_derive_workflow_graph_detects_preferences_edge() -> None:
    messages = make_page(
        "0001-messages",
        "https://example.com/message/index.php",
        page_type=PageType.MESSAGES,
        actions=[
            ActionAffordance(
                label="Notification preferences",
                url="https://example.com/message/notificationpreferences.php",
                element_type=AffordanceElementType.LINK,
            )
        ],
    )
    prefs = make_page(
        "0002-prefs",
        "https://example.com/message/notificationpreferences.php",
        page_type=PageType.MESSAGE_PREFERENCES,
    )

    graph = derive_workflow_graph([messages, prefs])

    assert graph.edges[0].edge_type == WorkflowEdgeType.PREFERENCES
    assert graph.edge_type_counts["preferences"] == 1
    assert graph.edge_weight_counts["high"] == 1
    assert graph.edge_relevance_counts["task"] == 1


def test_derive_workflow_graph_marks_admin_navigation() -> None:
    admin_root = make_page(
        "0001-admin",
        "https://example.com/admin/search.php",
        page_type=PageType.ADMIN_SEARCH,
        tabs=[TabAffordance(label="Registration", url="https://example.com/admin/registration/index.php")],
    )
    admin_child = make_page(
        "0002-registration",
        "https://example.com/admin/registration/index.php",
        page_type=PageType.ADMIN_SETTING_PAGE,
        crawl_depth=1,
        title="Registration | Moodle Demo",
        breadcrumbs=["Administration", "Registration"],
    )

    graph = derive_workflow_graph([admin_root, admin_child])

    assert graph.edges[0].edge_type == WorkflowEdgeType.ADMIN
    assert graph.edges[0].source_affordance_kind == "tab"
    assert graph.edges[0].edge_weight == EdgeWeight.HIGH
    assert graph.edges[0].edge_relevance == EdgeRelevance.TASK


def test_derive_workflow_graph_uses_related_fallback_for_discovered_links() -> None:
    source = make_page(
        "0001-course",
        "https://example.com/course/view.php?id=4",
        page_type=PageType.COURSE_VIEW,
    )
    source.discovered_links = ["https://example.com/reportbuilder/index.php"]
    target = make_page(
        "0002-reportbuilder",
        "https://example.com/reportbuilder/index.php",
        page_type=PageType.REPORT_BUILDER,
    )

    graph = derive_workflow_graph([source, target])

    assert graph.edges[0].edge_type == WorkflowEdgeType.RELATED
    assert graph.edges[0].source_affordance_kind == "discovered_link"
    assert graph.edges[0].edge_weight == EdgeWeight.LOW
    assert graph.edges[0].edge_relevance == EdgeRelevance.CONTEXTUAL


def test_next_steps_prefers_primary_task_edges_over_generic_navigation() -> None:
    course = make_page(
        "0001-course",
        "https://example.com/course/view.php?id=4",
        page_type=PageType.COURSE_VIEW,
        actions=[
            ActionAffordance(
                label="Edit course settings",
                url="https://example.com/course/edit.php?id=4",
                element_type=AffordanceElementType.LINK,
                importance_level=ImportanceLevel.PRIMARY,
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
        navigation=[
            NavigationItem(
                label="Calendar",
                url="https://example.com/calendar/view.php?view=month",
                current=False,
                importance_level=ImportanceLevel.SECONDARY,
                likely_intent=LikelyIntent.NAVIGATE,
            )
        ],
        task_summary=PageTaskSummary(primary_page_intent=LikelyIntent.CONFIGURE, task_relevance_score=80),
    )
    edit_page = make_page(
        "0002-edit",
        "https://example.com/course/edit.php?id=4",
        page_type=PageType.COURSE_EDIT,
    )
    calendar_page = make_page(
        "0003-calendar",
        "https://example.com/calendar/view.php?view=month",
        page_type=PageType.CALENDAR,
    )

    derive_workflow_graph([course, edit_page, calendar_page])

    assert course.next_steps[0].page_id == "0002-edit"
    assert course.next_steps[0].edge_relevance == EdgeRelevance.TASK
    assert course.next_steps[0].edge_weight == EdgeWeight.HIGH


def test_dashboard_next_steps_keep_secondary_user_surface_hops() -> None:
    dashboard = make_page(
        "0001-my",
        "https://example.com/my",
        page_type=PageType.DASHBOARD,
        task_summary=PageTaskSummary(primary_page_intent=LikelyIntent.NAVIGATE, task_relevance_score=80),
    )
    dashboard.discovered_links = [
        "https://example.com/course/view.php?id=4",
        "https://example.com/user/preferences.php",
        "https://example.com/user/profile.php",
        "https://example.com/calendar/view.php?view=month",
    ]
    course = make_page("0002-course", "https://example.com/course/view.php?id=4", page_type=PageType.COURSE_VIEW)
    prefs = make_page("0003-prefs", "https://example.com/user/preferences.php", page_type=PageType.USER_PREFERENCES)
    profile = make_page("0004-profile", "https://example.com/user/profile.php", page_type=PageType.USER_PROFILE)
    calendar = make_page("0005-calendar", "https://example.com/calendar/view.php?view=month", page_type=PageType.CALENDAR)

    derive_workflow_graph([dashboard, course, prefs, profile, calendar])

    next_step_targets = [step.target_page_type for step in dashboard.next_steps]
    assert next_step_targets[0] == PageType.COURSE_VIEW
    assert PageType.USER_PREFERENCES in next_step_targets
    assert PageType.USER_PROFILE in next_step_targets


def test_admin_search_prefers_specific_setting_page_over_broad_admin_category() -> None:
    admin_search = make_page(
        "0001-admin-search",
        "https://example.com/admin/search.php",
        page_type=PageType.ADMIN_SEARCH,
        navigation=[
            NavigationItem(
                label="AI settings",
                url="https://example.com/admin/settings.php?section=aiprovider",
                current=False,
                importance_level=ImportanceLevel.SECONDARY,
                likely_intent=LikelyIntent.CONFIGURE,
            ),
            NavigationItem(
                label="Competencies",
                url="https://example.com/admin/category.php?category=competencies",
                current=False,
                importance_level=ImportanceLevel.SECONDARY,
                likely_intent=LikelyIntent.NAVIGATE,
            ),
        ],
        task_summary=PageTaskSummary(primary_page_intent=LikelyIntent.CONFIGURE, task_relevance_score=85),
    )
    admin_setting = make_page(
        "0002-admin-setting",
        "https://example.com/admin/settings.php?section=aiprovider",
        page_type=PageType.ADMIN_SETTING_PAGE,
    )
    admin_category = make_page(
        "0003-admin-category",
        "https://example.com/admin/category.php?category=competencies",
        page_type=PageType.ADMIN_CATEGORY,
    )

    derive_workflow_graph([admin_search, admin_setting, admin_category])

    assert admin_search.next_steps[0].page_id == "0002-admin-setting"
    assert admin_search.next_steps[0].edge_weight == EdgeWeight.HIGH
    assert admin_search.next_steps[0].edge_relevance == EdgeRelevance.TASK


def test_stronger_explicit_edge_prunes_weaker_discovered_link_duplicate() -> None:
    source = make_page(
        "0001-admin-search",
        "https://example.com/admin/search.php",
        page_type=PageType.ADMIN_SEARCH,
        navigation=[
            NavigationItem(
                label="AI providers",
                url="https://example.com/admin/settings.php?section=aiprovider",
                current=False,
                importance_level=ImportanceLevel.SECONDARY,
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
    )
    source.discovered_links = ["https://example.com/admin/settings.php?section=aiprovider"]
    target = make_page(
        "0002-admin-setting",
        "https://example.com/admin/settings.php?section=aiprovider",
        page_type=PageType.ADMIN_SETTING_PAGE,
    )

    graph = derive_workflow_graph([source, target])

    assert graph.candidate_edge_count == 1
    assert graph.total_edges == 1
    assert graph.suppressed_edge_count == 0
    assert graph.edges[0].source_affordance_kind == "navigation"
    assert graph.edges[0].edge_relevance == EdgeRelevance.TASK


def test_same_source_target_pair_keeps_stronger_edge_only() -> None:
    source = make_page(
        "0001-course",
        "https://example.com/course/view.php?id=4",
        page_type=PageType.COURSE_VIEW,
        actions=[
            ActionAffordance(
                label="Edit settings",
                url="https://example.com/course/edit.php?id=4",
                element_type=AffordanceElementType.LINK,
                importance_level=ImportanceLevel.PRIMARY,
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
        navigation=[
            NavigationItem(
                label="Settings",
                url="https://example.com/course/edit.php?id=4",
                current=False,
                importance_level=ImportanceLevel.SECONDARY,
                likely_intent=LikelyIntent.NAVIGATE,
            )
        ],
    )
    target = make_page(
        "0002-edit",
        "https://example.com/course/edit.php?id=4",
        page_type=PageType.COURSE_EDIT,
    )

    graph = derive_workflow_graph([source, target])

    assert graph.candidate_edge_count == 2
    assert graph.total_edges == 1
    assert graph.suppressed_edge_count == 1
    assert graph.deduplicated_pair_count == 1
    assert graph.edges[0].source_affordance_kind == "link"


def test_calendar_discovered_link_variants_are_grouped_for_same_source_page() -> None:
    source = make_page(
        "0001-dashboard",
        "https://example.com/my",
        page_type=PageType.DASHBOARD,
    )
    source.discovered_links = [
        "https://example.com/calendar/view.php?view=month",
        "https://example.com/calendar/view.php?time=1&view=month",
        "https://example.com/calendar/view.php?time=2&view=month",
    ]
    target = make_page(
        "0002-calendar",
        "https://example.com/calendar/view.php?view=month",
        page_type=PageType.CALENDAR,
    )

    graph = derive_workflow_graph([source, target])

    assert graph.candidate_edge_count == 1
    assert graph.total_edges == 0
    assert graph.cluster_count == 1
    assert graph.compressed_edge_count == 1
    assert source.background_navigation_clusters[0].family_key == "/calendar/view.php"
    assert source.next_steps[0].page_id == "0002-calendar"
    assert source.next_steps[0].target_page_type == PageType.CALENDAR
    assert source.next_steps[0].notes == "background-cluster-first-hop"


def test_next_steps_drop_contextual_noise_when_task_edges_exist() -> None:
    source = make_page(
        "0001-messages",
        "https://example.com/message/index.php",
        page_type=PageType.MESSAGES,
        actions=[
            ActionAffordance(
                label="Notification preferences",
                url="https://example.com/message/notificationpreferences.php",
                element_type=AffordanceElementType.LINK,
                importance_level=ImportanceLevel.SECONDARY,
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
        task_summary=PageTaskSummary(primary_page_intent=LikelyIntent.CONFIGURE, task_relevance_score=70),
    )
    source.discovered_links = ["https://example.com/calendar/view.php?view=month"]
    prefs = make_page(
        "0002-prefs",
        "https://example.com/message/notificationpreferences.php",
        page_type=PageType.MESSAGE_PREFERENCES,
    )
    calendar = make_page(
        "0003-calendar",
        "https://example.com/calendar/view.php?view=month",
        page_type=PageType.CALENDAR,
    )

    derive_workflow_graph([source, prefs, calendar])

    assert source.next_steps[0].page_id == "0002-prefs"
    assert all(step.page_id != "0003-calendar" for step in source.next_steps)


def test_admin_low_value_edges_are_compressed_into_background_clusters() -> None:
    source = make_page(
        "0001-admin-search",
        "https://example.com/admin/search.php",
        page_type=PageType.ADMIN_SEARCH,
        task_summary=PageTaskSummary(primary_page_intent=LikelyIntent.SEARCH, task_relevance_score=90),
    )
    source.discovered_links = [
        "https://example.com/admin/category.php?category=one",
        "https://example.com/admin/category.php?category=two",
        "https://example.com/admin/search.php#users",
    ]
    admin_category_a = make_page(
        "0002-admin-category-a",
        "https://example.com/admin/category.php?category=one",
        page_type=PageType.ADMIN_CATEGORY,
    )
    admin_category_b = make_page(
        "0003-admin-category-b",
        "https://example.com/admin/category.php?category=two",
        page_type=PageType.ADMIN_CATEGORY,
    )
    admin_search = make_page(
        "0004-admin-search-self",
        "https://example.com/admin/search.php#users",
        page_type=PageType.ADMIN_SEARCH,
    )

    graph = derive_workflow_graph([source, admin_category_a, admin_category_b, admin_search])

    assert graph.cluster_count >= 1
    assert graph.compressed_edge_count == 2
    assert source.background_navigation_clusters
    assert any(cluster.family_key == "/admin/category.php" for cluster in source.background_navigation_clusters)
    assert all(edge.target_url != "https://example.com/admin/category.php?category=one" for edge in graph.edges)


def test_calendar_low_value_edges_are_compressed_but_task_edges_remain() -> None:
    source = make_page(
        "0001-dashboard",
        "https://example.com/my",
        page_type=PageType.DASHBOARD,
        navigation=[
            NavigationItem(
                label="Course 1",
                url="https://example.com/course/view.php?id=4",
                current=False,
                importance_level=ImportanceLevel.SECONDARY,
                likely_intent=LikelyIntent.NAVIGATE,
            )
        ],
    )
    source.discovered_links = [
        "https://example.com/calendar/view.php?view=month",
        "https://example.com/calendar/view.php?time=1&view=month",
    ]
    course = make_page(
        "0002-course",
        "https://example.com/course/view.php?id=4",
        page_type=PageType.COURSE_VIEW,
    )
    calendar = make_page(
        "0003-calendar",
        "https://example.com/calendar/view.php?view=month",
        page_type=PageType.CALENDAR,
    )

    graph = derive_workflow_graph([source, course, calendar])

    assert graph.total_edges == 1
    assert graph.edges[0].to_page_id == "0002-course"
    assert graph.compressed_edge_count == 1
    assert source.background_navigation_clusters[0].family_key == "/calendar/view.php"
    assert [step.page_id for step in source.next_steps] == ["0002-course", "0003-calendar"]
