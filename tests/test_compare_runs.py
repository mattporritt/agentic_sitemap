# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from datetime import datetime, timezone
from pathlib import Path

from moodle_sitemap.compare_runs import build_run_comparison_summary, create_compare_run_dir
from moodle_sitemap.models import (
    ActionAffordance,
    AffordanceElementType,
    EdgeRelevance,
    EdgeWeight,
    LikelyIntent,
    NextStepHint,
    PageAffordances,
    PageRecord,
    PageRiskLevel,
    PageSafetySummary,
    PageType,
    SiteManifest,
    WorkflowEdge,
    WorkflowEdgeType,
    WorkflowGraph,
)


def make_page(page_id: str, url: str, *, page_type: PageType, actions: list[ActionAffordance] | None = None) -> PageRecord:
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


def test_build_run_comparison_summary_reports_page_and_edge_differences(tmp_path: Path) -> None:
    left_pages = [
        make_page(
            "0001-my",
            "https://example.com/my",
            page_type=PageType.DASHBOARD,
            actions=[
                ActionAffordance(label="Course 1", url="https://example.com/course/view.php?id=4", element_type=AffordanceElementType.LINK)
            ],
        ),
        make_page("0002-course", "https://example.com/course/view.php?id=4", page_type=PageType.COURSE_VIEW),
    ]
    right_pages = [
        make_page("0001-my", "https://example.com/my", page_type=PageType.DASHBOARD),
        make_page("0003-message", "https://example.com/message/index.php", page_type=PageType.MESSAGES),
    ]
    left_manifest = make_manifest("teacher", left_pages)
    right_manifest = make_manifest("student", right_pages)
    left_graph = WorkflowGraph(
        role_profile="teacher",
        total_edges=1,
        edge_type_counts={"navigation": 1},
        edges=[
            WorkflowEdge(
                from_page_id="0001-my",
                to_page_id="0002-course",
                target_url="https://example.com/course/view.php?id=4",
                edge_type=WorkflowEdgeType.NAVIGATION,
                source_affordance_label="Course 1",
                source_affordance_kind="link",
                confidence=0.95,
            )
        ],
    )
    right_graph = WorkflowGraph(
        role_profile="student",
        total_edges=1,
        edge_type_counts={"preferences": 1},
        edges=[
            WorkflowEdge(
                from_page_id="0001-my",
                to_page_id="0003-message",
                target_url="https://example.com/message/index.php",
                edge_type=WorkflowEdgeType.RELATED,
            )
        ],
    )

    summary = build_run_comparison_summary(
        left_run_dir=tmp_path / "left",
        right_run_dir=tmp_path / "right",
        left_manifest=left_manifest,
        right_manifest=right_manifest,
        left_graph=left_graph,
        right_graph=right_graph,
    )

    assert summary.left_role_profile == "teacher"
    assert summary.right_role_profile == "student"
    assert summary.shared_page_count == 1
    assert summary.left_task_edges == 0
    assert summary.right_task_edges == 0
    assert summary.pages_only_in_left == ["https://example.com/course/view.php?id=4"]
    assert summary.pages_only_in_right == ["https://example.com/message/index.php"]
    assert summary.edge_signatures_only_in_left == [
        "navigation:https://example.com/my->https://example.com/course/view.php?id=4"
    ]
    assert summary.affordance_differences[0]["normalized_url"] == "https://example.com/my"


def test_build_run_comparison_summary_reports_next_step_and_safety_differences(tmp_path: Path) -> None:
    left_page = make_page("0001-course", "https://example.com/course/view.php?id=4", page_type=PageType.COURSE_VIEW)
    right_page = make_page("0001-course", "https://example.com/course/view.php?id=4", page_type=PageType.COURSE_VIEW)
    left_page.next_steps = [
        NextStepHint(
            page_id="0002-edit",
            target_url="https://example.com/course/edit.php?id=4",
            edge_type=WorkflowEdgeType.EDIT,
            edge_weight=EdgeWeight.HIGH,
            edge_relevance=EdgeRelevance.TASK,
            label="Edit settings",
            likely_intent=LikelyIntent.EDIT,
        )
    ]
    right_page.next_steps = [
        NextStepHint(
            page_id="0003-gradebook",
            target_url="https://example.com/grade/report/overview/index.php",
            edge_type=WorkflowEdgeType.RELATED,
            edge_weight=EdgeWeight.MEDIUM,
            edge_relevance=EdgeRelevance.SUPPORT,
            label="Grades",
            likely_intent=LikelyIntent.VIEW,
        )
    ]
    left_page.safety = PageSafetySummary(
        page_risk_level=PageRiskLevel.HIGH,
        contains_mutating_actions=True,
        mutating_action_count=3,
        contains_destructive_actions=False,
    )
    right_page.safety = PageSafetySummary(
        page_risk_level=PageRiskLevel.LOW,
        contains_mutating_actions=False,
        mutating_action_count=0,
        contains_destructive_actions=False,
    )

    left_manifest = make_manifest("teacher", [left_page])
    right_manifest = make_manifest("student", [right_page])
    left_graph = WorkflowGraph(
        role_profile="teacher",
        total_edges=1,
        edge_type_counts={"edit": 1},
        edges=[
            WorkflowEdge(
                from_page_id="0001-course",
                to_page_id="0002-edit",
                target_url="https://example.com/course/edit.php?id=4",
                edge_type=WorkflowEdgeType.EDIT,
                edge_weight=EdgeWeight.HIGH,
                edge_relevance=EdgeRelevance.TASK,
            )
        ],
    )
    right_graph = WorkflowGraph(role_profile="student", total_edges=0, edge_type_counts={}, edges=[])

    summary = build_run_comparison_summary(
        left_run_dir=tmp_path / "left",
        right_run_dir=tmp_path / "right",
        left_manifest=left_manifest,
        right_manifest=right_manifest,
        left_graph=left_graph,
        right_graph=right_graph,
    )

    assert summary.left_task_edges == 1
    assert summary.right_task_edges == 0
    assert summary.next_step_differences[0]["next_steps_only_in_left"] == ["Edit settings"]
    assert summary.next_step_differences[0]["next_steps_only_in_right"] == ["Grades"]
    assert summary.safety_differences[0]["left_risk_level"] == "high"
    assert summary.safety_differences[0]["right_risk_level"] == "low"


def test_create_compare_run_dir_avoids_same_second_collisions(tmp_path: Path) -> None:
    first = create_compare_run_dir(tmp_path)
    second = create_compare_run_dir(tmp_path)

    assert first.exists()
    assert second.exists()
    assert first != second
