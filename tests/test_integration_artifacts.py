# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from moodle_sitemap.compare_runs import compare_runs
from moodle_sitemap.models import (
    ActionAffordance,
    AffordanceElementType,
    EdgeRelevance,
    EdgeWeight,
    LikelyIntent,
    NextStepHint,
    PageAffordances,
    PageRecord,
    PageType,
    SiteManifest,
    TaskSpecList,
    WorkflowEdge,
    WorkflowEdgeType,
    WorkflowGraph,
)
from moodle_sitemap.task_validation import validate_tasks_for_run


def make_page(
    page_id: str,
    url: str,
    *,
    page_type: PageType,
    actions: list[ActionAffordance] | None = None,
    next_steps: list[NextStepHint] | None = None,
    primary_page_intent: LikelyIntent = LikelyIntent.UNKNOWN,
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
        primary_page_intent=primary_page_intent,
        next_steps=next_steps or [],
        discovered_links=[],
        network=[],
    )


def make_manifest(role_profile: str, pages: list[PageRecord], workflow_edge_count: int = 0) -> SiteManifest:
    started = datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 4, 10, 0, 1, 0, tzinfo=timezone.utc)
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
            "workflow_edge_count": workflow_edge_count,
            "page_type_counts": {page_type.value: sum(1 for page in pages if page.page_type == page_type) for page_type in PageType},
            "crawl_started_at": started,
            "crawl_finished_at": ended,
        },
        pages=pages,
    )


def write_saved_run(run_dir: Path, manifest: SiteManifest, graph: WorkflowGraph) -> None:
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "sitemap.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "workflow-edges.json").write_text(graph.model_dump_json(indent=2), encoding="utf-8")


def test_validate_tasks_for_run_reads_saved_artifacts_and_writes_results(tmp_path: Path) -> None:
    dashboard = make_page(
        "0001-my",
        "https://example.com/my",
        page_type=PageType.DASHBOARD,
        primary_page_intent=LikelyIntent.NAVIGATE,
        next_steps=[
            NextStepHint(
                page_id="0002-prefs",
                target_url="https://example.com/message/notificationpreferences.php",
                target_page_type=PageType.MESSAGE_PREFERENCES,
                edge_type=WorkflowEdgeType.PREFERENCES,
                edge_weight=EdgeWeight.HIGH,
                edge_relevance=EdgeRelevance.TASK,
                label="Notification preferences",
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
    )
    prefs = make_page(
        "0002-prefs",
        "https://example.com/message/notificationpreferences.php",
        page_type=PageType.MESSAGE_PREFERENCES,
        actions=[
            ActionAffordance(
                label="Notification preferences",
                element_type=AffordanceElementType.LINK,
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
        primary_page_intent=LikelyIntent.CONFIGURE,
    )
    manifest = make_manifest("student", [dashboard, prefs], workflow_edge_count=1)
    graph = WorkflowGraph(
        role_profile="student",
        total_edges=1,
        edges=[
            WorkflowEdge(
                from_page_id="0001-my",
                to_page_id="0002-prefs",
                target_url="https://example.com/message/notificationpreferences.php",
                target_page_type=PageType.MESSAGE_PREFERENCES,
                edge_type=WorkflowEdgeType.PREFERENCES,
                edge_weight=EdgeWeight.HIGH,
                edge_relevance=EdgeRelevance.TASK,
                source_affordance_label="Notification preferences",
                confidence=0.95,
            )
        ],
    )
    run_dir = tmp_path / "run"
    write_saved_run(run_dir, manifest, graph)

    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        TaskSpecList.model_validate(
            {
                "tasks": [
                    {
                        "task_id": "message-preferences",
                        "role_profile": "student",
                        "starting_page_type": "dashboard",
                        "target_page_type": "message_preferences",
                        "required_affordance_intents": ["configure"],
                        "success_hint": "Reach notification preferences",
                    }
                ]
            }
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )

    result = validate_tasks_for_run(run_dir=run_dir, tasks_path=tasks_path, base_dir=tmp_path / "task-output")

    assert result.output_dir.exists()
    assert result.summary.pass_count == 1
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["role_profile"] == "student"
    assert payload["results"][0]["status"] == "pass"
    assert payload["results"][0]["first_hop_quality"] >= 90


def test_compare_runs_writes_role_specific_artifacts_from_saved_runs(tmp_path: Path) -> None:
    shared_left = make_page(
        "0001-my",
        "https://example.com/my",
        page_type=PageType.DASHBOARD,
        actions=[ActionAffordance(label="Course 1", element_type=AffordanceElementType.LINK)],
        primary_page_intent=LikelyIntent.NAVIGATE,
    )
    shared_right = make_page(
        "0001-my",
        "https://example.com/my",
        page_type=PageType.DASHBOARD,
        actions=[ActionAffordance(label="Messages", element_type=AffordanceElementType.LINK)],
        primary_page_intent=LikelyIntent.NAVIGATE,
    )
    left_only = make_page("0002-course", "https://example.com/course/view.php?id=4", page_type=PageType.COURSE_VIEW)
    right_only = make_page("0003-message", "https://example.com/message/index.php", page_type=PageType.MESSAGES)
    left_manifest = make_manifest("teacher", [shared_left, left_only], workflow_edge_count=1)
    right_manifest = make_manifest("student", [shared_right, right_only], workflow_edge_count=1)
    left_graph = WorkflowGraph(
        role_profile="teacher",
        total_edges=1,
        edges=[
            WorkflowEdge(
                from_page_id="0001-my",
                to_page_id="0002-course",
                target_url="https://example.com/course/view.php?id=4",
                target_page_type=PageType.COURSE_VIEW,
                edge_type=WorkflowEdgeType.NAVIGATION,
                edge_weight=EdgeWeight.HIGH,
                edge_relevance=EdgeRelevance.TASK,
            )
        ],
    )
    right_graph = WorkflowGraph(
        role_profile="student",
        total_edges=1,
        edges=[
            WorkflowEdge(
                from_page_id="0001-my",
                to_page_id="0003-message",
                target_url="https://example.com/message/index.php",
                target_page_type=PageType.MESSAGES,
                edge_type=WorkflowEdgeType.RELATED,
                edge_weight=EdgeWeight.LOW,
                edge_relevance=EdgeRelevance.CONTEXTUAL,
            )
        ],
    )

    left_dir = tmp_path / "teacher-run"
    right_dir = tmp_path / "student-run"
    write_saved_run(left_dir, left_manifest, left_graph)
    write_saved_run(right_dir, right_manifest, right_graph)

    result = compare_runs(left_run_dir=left_dir, right_run_dir=right_dir, base_dir=tmp_path / "compare-output")

    assert result.output_dir.exists()
    assert result.json_path.name == "role-compare-teacher-vs-student.json"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["left_role_profile"] == "teacher"
    assert payload["right_role_profile"] == "student"
    assert payload["pages_only_in_left"] == ["https://example.com/course/view.php?id=4"]
    assert payload["pages_only_in_right"] == ["https://example.com/message/index.php"]
