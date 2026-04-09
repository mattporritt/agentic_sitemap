import json
from datetime import datetime, timezone
from pathlib import Path

from moodle_sitemap.models import (
    ActionAffordance,
    AffordanceElementType,
    BackgroundNavigationCluster,
    EdgeRelevance,
    EdgeWeight,
    LikelyIntent,
    NextStepHint,
    PageAffordances,
    PageRecord,
    PageType,
    SiteManifest,
    TaskSpec,
    TaskValidationStatus,
    WorkflowEdge,
    WorkflowEdgeType,
    WorkflowGraph,
)
from moodle_sitemap.task_validation import (
    collect_key_affordances,
    evaluate_task,
    load_task_specs,
)


def make_page(
    page_id: str,
    url: str,
    *,
    page_type: PageType,
    actions: list[ActionAffordance] | None = None,
    next_steps: list[NextStepHint] | None = None,
) -> PageRecord:
    return PageRecord(
        page_id=page_id,
        url=url,
        normalized_url=url,
        final_url=url,
        title=page_id,
        page_type=page_type,
        body_classes=[],
        breadcrumbs=[],
        affordances=PageAffordances(actions=actions or []),
        next_steps=next_steps or [],
        discovered_links=[],
        network=[],
    )


def make_manifest(role_profile: str, pages: list[PageRecord]) -> SiteManifest:
    started = datetime(2026, 4, 8, 10, 0, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 4, 8, 10, 1, 0, tzinfo=timezone.utc)
    return SiteManifest(
        site_url="https://example.com",
        role_profile=role_profile,
        origin="https://example.com",
        crawl_started_at=started,
        crawl_finished_at=ended,
        max_pages=25,
        visited_pages=len(pages),
        summary={
            "total_pages": len(pages),
            "unknown_pages": sum(1 for page in pages if page.page_type == PageType.UNKNOWN),
            "workflow_edge_count": 1,
            "page_type_counts": {page_type.value: sum(1 for page in pages if page.page_type == page_type) for page_type in PageType},
            "crawl_started_at": started,
            "crawl_finished_at": ended,
        },
        pages=pages,
    )


def test_load_task_specs(tmp_path: Path) -> None:
    task_file = tmp_path / "tasks.json"
    task_file.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_id": "find-calendar",
                        "role_profile": "student",
                        "starting_page_type": "dashboard",
                        "target_page_type": "calendar",
                        "success_hint": "Find calendar",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    loaded = load_task_specs(task_file)
    assert loaded.tasks[0].task_id == "find-calendar"
    assert loaded.tasks[0].target_page_type == PageType.CALENDAR


def test_evaluate_task_passes_when_target_and_path_are_clear() -> None:
    dashboard = make_page(
        "0001-my",
        "https://example.com/my",
        page_type=PageType.DASHBOARD,
        next_steps=[
            NextStepHint(
                page_id="0002-msgprefs",
                target_url="https://example.com/message/notificationpreferences.php",
                edge_type=WorkflowEdgeType.PREFERENCES,
                edge_weight=EdgeWeight.HIGH,
                edge_relevance=EdgeRelevance.TASK,
                label="Notification preferences",
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
    )
    target = make_page(
        "0002-msgprefs",
        "https://example.com/message/notificationpreferences.php",
        page_type=PageType.MESSAGE_PREFERENCES,
        actions=[
            ActionAffordance(
                label="Notification preferences",
                url="https://example.com/message/notificationpreferences.php",
                element_type=AffordanceElementType.LINK,
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
    )
    manifest = make_manifest("student", [dashboard, target])
    graph = WorkflowGraph(
        role_profile="student",
        total_edges=1,
        edges=[
            WorkflowEdge(
                from_page_id="0001-my",
                to_page_id="0002-msgprefs",
                target_url="https://example.com/message/notificationpreferences.php",
                edge_type=WorkflowEdgeType.PREFERENCES,
                edge_weight=EdgeWeight.HIGH,
                edge_relevance=EdgeRelevance.TASK,
                source_affordance_label="Notification preferences",
                confidence=0.95,
            )
        ],
    )
    task = TaskSpec(
        task_id="message-preferences",
        role_profile="student",
        starting_page_type=PageType.DASHBOARD,
        target_page_type=PageType.MESSAGE_PREFERENCES,
        required_affordance_intents=[LikelyIntent.CONFIGURE],
        success_hint="Reach message preferences",
    )

    result = evaluate_task(task=task, manifest=manifest, workflow_graph=graph)

    assert result.status == TaskValidationStatus.PASS
    assert result.path_length == 1
    assert result.next_steps_helpful is True
    assert result.first_hop_quality >= 90


def test_evaluate_task_is_partial_when_target_exists_without_path() -> None:
    dashboard = make_page("0001-my", "https://example.com/my", page_type=PageType.DASHBOARD)
    target = make_page(
        "0002-course",
        "https://example.com/course/view.php?id=4",
        page_type=PageType.COURSE_VIEW,
        actions=[
            ActionAffordance(
                label="Settings",
                element_type=AffordanceElementType.LINK,
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
    )
    manifest = make_manifest("teacher", [dashboard, target])
    task = TaskSpec(
        task_id="course-configure",
        role_profile="teacher",
        starting_page_type=PageType.DASHBOARD,
        target_page_type=PageType.COURSE_VIEW,
        required_affordance_intents=[LikelyIntent.CONFIGURE],
        success_hint="Reach configurable course page",
    )

    result = evaluate_task(task=task, manifest=manifest, workflow_graph=None)

    assert result.status == TaskValidationStatus.PARTIAL
    assert "no-plausible-path-in-graph" in result.blockers


def test_evaluate_task_fails_when_target_is_missing() -> None:
    dashboard = make_page("0001-my", "https://example.com/my", page_type=PageType.DASHBOARD)
    manifest = make_manifest("admin", [dashboard])
    task = TaskSpec(
        task_id="find-ai-settings",
        role_profile="admin",
        starting_page_type=PageType.DASHBOARD,
        target_page_type=PageType.ADMIN_SETTING_PAGE,
        target_url_contains=["aiplacement"],
        success_hint="Reach AI settings",
    )

    result = evaluate_task(task=task, manifest=manifest, workflow_graph=None)

    assert result.status == TaskValidationStatus.FAIL
    assert "target-page-not-found" in result.blockers


def test_collect_key_affordances_prefers_task_relevant_controls_over_generic_links() -> None:
    target = make_page(
        "0002-msgprefs",
        "https://example.com/message/notificationpreferences.php",
        page_type=PageType.MESSAGE_PREFERENCES,
        actions=[
            ActionAffordance(
                label="Skip to main content",
                element_type=AffordanceElementType.LINK,
                likely_intent=LikelyIntent.NAVIGATE,
            ),
            ActionAffordance(
                label="Notification preferences",
                element_type=AffordanceElementType.LINK,
                likely_intent=LikelyIntent.CONFIGURE,
            ),
            ActionAffordance(
                label="Message email notifications",
                element_type=AffordanceElementType.LINK,
                likely_intent=LikelyIntent.CONFIGURE,
            ),
        ],
    )
    task = TaskSpec(
        task_id="message-preferences",
        role_profile="student",
        target_page_type=PageType.MESSAGE_PREFERENCES,
        required_affordance_intents=[LikelyIntent.CONFIGURE],
        success_hint="Reach message preferences",
    )

    labels = collect_key_affordances(task, [target])

    assert labels[:2] == ["Message email notifications", "Notification preferences"]
    assert "Skip to main content" not in labels


def test_evaluate_task_uses_background_cluster_path_for_calendar_surface() -> None:
    dashboard = make_page("0001-my", "https://example.com/my", page_type=PageType.DASHBOARD)
    dashboard.background_navigation_clusters = [
        BackgroundNavigationCluster(
            cluster_type="repeated_variant_cluster",
            source_page_id="0001-my",
            family_key="/calendar/view.php",
            count=3,
            representative_targets=["https://example.com/calendar/view.php?view=month"],
            edge_relevance=EdgeRelevance.CONTEXTUAL,
            edge_weight=EdgeWeight.LOW,
            reason_hint="compressed-calendar-variants",
        )
    ]
    target = make_page(
        "0002-calendar",
        "https://example.com/calendar/view.php?view=month",
        page_type=PageType.CALENDAR,
        actions=[
            ActionAffordance(
                label="Import or export calendars",
                element_type=AffordanceElementType.LINK,
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
    )
    manifest = make_manifest("admin", [dashboard, target])
    task = TaskSpec(
        task_id="calendar",
        role_profile="admin",
        starting_page_type=PageType.DASHBOARD,
        target_page_type=PageType.CALENDAR,
        success_hint="Reach a calendar page from the dashboard.",
    )

    result = evaluate_task(task=task, manifest=manifest, workflow_graph=None)

    assert result.status == TaskValidationStatus.PASS
    assert result.candidate_path_page_types == ["dashboard", "calendar"]
    assert result.best_path_confidence == 45
    assert result.first_hop_quality >= 30
