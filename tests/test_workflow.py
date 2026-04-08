from moodle_sitemap.models import (
    ActionAffordance,
    AffordanceElementType,
    NavigationItem,
    NextStepHint,
    PageAffordances,
    PageRecord,
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
    assert graph.edges[0].to_page_id == "0002-course"
    assert dashboard.next_steps[0] == NextStepHint(
        page_id="0002-course",
        target_url="https://example.com/course/view.php?id=4",
        edge_type=WorkflowEdgeType.NAVIGATION,
        label="Course 1",
        confidence=0.95,
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


def test_derive_workflow_graph_marks_admin_navigation() -> None:
    admin_root = make_page(
        "0001-admin",
        "https://example.com/admin/search.php",
        page_type=PageType.ADMIN_SETTINGS,
        tabs=[TabAffordance(label="Registration", url="https://example.com/admin/registration/index.php")],
    )
    admin_child = make_page(
        "0002-registration",
        "https://example.com/admin/registration/index.php",
        page_type=PageType.ADMIN_SETTINGS,
        crawl_depth=1,
        title="Registration | Moodle Demo",
        breadcrumbs=["Administration", "Registration"],
    )

    graph = derive_workflow_graph([admin_root, admin_child])

    assert graph.edges[0].edge_type == WorkflowEdgeType.ADMIN
    assert graph.edges[0].source_affordance_kind == "tab"


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
