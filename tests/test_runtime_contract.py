from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from moodle_sitemap.cli import app
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

runner = CliRunner()


def make_page(
    page_id: str,
    url: str,
    *,
    page_type: PageType,
    next_steps: list[NextStepHint] | None = None,
    actions: list[ActionAffordance] | None = None,
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
        primary_page_intent=LikelyIntent.NAVIGATE,
        primary_actions=[],
        task_relevance_score=50,
        discovered_links=[],
        network=[],
    )


def make_manifest(role_profile: str, pages: list[PageRecord], workflow_edge_count: int = 0) -> SiteManifest:
    started = datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 4, 11, 0, 1, 0, tzinfo=timezone.utc)
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


def assert_contract_envelope_shape(payload: dict[str, object]) -> None:
    assert set(payload.keys()) == {
        "tool",
        "version",
        "query",
        "normalized_query",
        "intent",
        "results",
    }
    assert isinstance(payload["results"], list)
    assert set(payload["intent"].keys()) == {
        "query_intent",
        "lookup_mode",
        "role_profile",
        "filters",
    }
    assert isinstance(payload["intent"]["filters"], list)


def assert_contract_result_shape(item: dict[str, object]) -> None:
    assert set(item.keys()) == {
        "id",
        "type",
        "rank",
        "confidence",
        "source",
        "content",
        "diagnostics",
    }
    assert isinstance(item["content"], dict)
    assert isinstance(item["diagnostics"], dict)
    assert set(item["source"].keys()) == {
        "name",
        "type",
        "url",
        "canonical_url",
        "path",
        "document_title",
        "section_title",
        "heading_path",
    }
    assert isinstance(item["source"]["heading_path"], list)


def test_runtime_query_page_json_contract_has_required_fields(tmp_path: Path) -> None:
    dashboard = make_page(
        "0001-my",
        "https://example.com/my",
        page_type=PageType.DASHBOARD,
        next_steps=[
            NextStepHint(
                page_id="0002-prefs",
                target_url="https://example.com/user/preferences.php",
                target_page_type=PageType.USER_PREFERENCES,
                edge_type=WorkflowEdgeType.NAVIGATION,
                edge_weight=EdgeWeight.MEDIUM,
                edge_relevance=EdgeRelevance.SUPPORT,
                label="Preferences",
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
    )
    prefs = make_page(
        "0002-prefs",
        "https://example.com/user/preferences.php",
        page_type=PageType.USER_PREFERENCES,
        actions=[
            ActionAffordance(
                label="Notification preferences",
                element_type=AffordanceElementType.LINK,
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
    )
    run_dir = tmp_path / "run"
    write_saved_run(
        run_dir,
        make_manifest("student", [dashboard, prefs], workflow_edge_count=1),
        WorkflowGraph(role_profile="student", total_edges=0, edges=[]),
    )

    result = runner.invoke(
        app,
        [
            "runtime-query",
            "--run",
            str(run_dir),
            "--lookup-mode",
            "page",
            "--query",
            "https://example.com/user/preferences.php",
            "--json-contract",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert_contract_envelope_shape(payload)
    assert payload["tool"] == "agentic_sitemap"
    assert payload["version"] == "v1"
    assert payload["query"] == "https://example.com/user/preferences.php"
    assert payload["normalized_query"] == "https://example.com/user/preferences.php"
    assert payload["intent"] == {
        "query_intent": "page_lookup",
        "lookup_mode": "page",
        "role_profile": "student",
        "filters": [],
    }
    assert isinstance(payload["results"], list)
    item = payload["results"][0]
    assert_contract_result_shape(item)
    assert item["type"] == "page_context"
    assert item["rank"] == 1
    assert item["confidence"] == "high"
    assert item["source"] == {
        "name": "moodle_site",
        "type": "site_crawl",
        "url": "https://example.com/user/preferences.php",
        "canonical_url": "https://example.com/user/preferences.php",
        "path": "/user/preferences.php",
        "document_title": "0002-prefs",
        "section_title": None,
        "heading_path": [],
    }
    assert item["content"]["next_steps"] == []
    assert item["diagnostics"]["lookup_mode"] == "page"


def test_runtime_query_path_json_contract_is_deterministic(tmp_path: Path) -> None:
    dashboard = make_page("0001-my", "https://example.com/my", page_type=PageType.DASHBOARD)
    prefs = make_page("0002-prefs", "https://example.com/user/preferences.php", page_type=PageType.USER_PREFERENCES)
    graph = WorkflowGraph(
        role_profile="student",
        total_edges=1,
        edges=[
            WorkflowEdge(
                from_page_id="0001-my",
                to_page_id="0002-prefs",
                target_url="https://example.com/user/preferences.php",
                target_page_type=PageType.USER_PREFERENCES,
                edge_type=WorkflowEdgeType.NAVIGATION,
                edge_weight=EdgeWeight.MEDIUM,
                edge_relevance=EdgeRelevance.SUPPORT,
                source_affordance_label="Preferences",
                confidence=0.78,
            )
        ],
    )
    run_dir = tmp_path / "run"
    write_saved_run(run_dir, make_manifest("student", [dashboard, prefs], workflow_edge_count=1), graph)

    args = [
        "runtime-query",
        "--run",
        str(run_dir),
        "--lookup-mode",
        "path",
        "--from-page",
        "dashboard",
        "--to-page",
        "user_preferences",
        "--json-contract",
    ]
    first = json.loads(runner.invoke(app, args).stdout)
    second = json.loads(runner.invoke(app, args).stdout)

    assert_contract_envelope_shape(first)
    assert_contract_result_shape(first["results"][0])
    assert first["results"][0]["id"] == second["results"][0]["id"]
    assert first["results"][0]["type"] == "site_path"
    assert first["results"][0]["content"]["page_types"] == ["dashboard", "user_preferences"]
    assert first["results"][0]["content"]["hops"][0]["target_page_type"] == "user_preferences"
    assert first["results"][0]["diagnostics"]["path_strategy"] == "workflow_graph_bfs"


def test_validate_tasks_json_contract_has_stable_result_shape(tmp_path: Path) -> None:
    dashboard = make_page(
        "0001-my",
        "https://example.com/my",
        page_type=PageType.DASHBOARD,
        next_steps=[
            NextStepHint(
                page_id="0002-msgprefs",
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
        "0002-msgprefs",
        "https://example.com/message/notificationpreferences.php",
        page_type=PageType.MESSAGE_PREFERENCES,
        actions=[
            ActionAffordance(
                label="Notification preferences",
                element_type=AffordanceElementType.LINK,
                likely_intent=LikelyIntent.CONFIGURE,
            )
        ],
    )
    graph = WorkflowGraph(
        role_profile="student",
        total_edges=1,
        edges=[
            WorkflowEdge(
                from_page_id="0001-my",
                to_page_id="0002-msgprefs",
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
    write_saved_run(run_dir, make_manifest("student", [dashboard, prefs], workflow_edge_count=1), graph)
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
                        "success_hint": "Reach message preferences",
                    }
                ]
            }
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "validate-tasks",
            "--run",
            str(run_dir),
            "--tasks",
            str(tasks_path),
            "--output-root",
            str(tmp_path / "task-output"),
            "--json-contract",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert_contract_envelope_shape(payload)
    assert_contract_result_shape(payload["results"][0])
    assert payload["tool"] == "agentic_sitemap"
    assert payload["intent"]["query_intent"] == "task_validation"
    assert payload["results"][0]["type"] == "task_validation"
    assert payload["results"][0]["source"]["heading_path"] == []
    assert payload["results"][0]["source"]["section_title"] is None
    assert payload["results"][0]["content"]["target_page_ids"] == ["0002-msgprefs"]
    assert payload["results"][0]["content"]["key_affordances"] == ["Notification preferences"]


def test_runtime_query_page_type_json_contract_has_full_result_shape(tmp_path: Path) -> None:
    prefs = make_page(
        "0002-prefs",
        "https://example.com/user/preferences.php",
        page_type=PageType.USER_PREFERENCES,
    )
    run_dir = tmp_path / "run"
    write_saved_run(
        run_dir,
        make_manifest("student", [prefs], workflow_edge_count=0),
        WorkflowGraph(role_profile="student", total_edges=0, edges=[]),
    )

    result = runner.invoke(
        app,
        [
            "runtime-query",
            "--run",
            str(run_dir),
            "--lookup-mode",
            "page_type",
            "--query",
            "user_preferences",
            "--json-contract",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert_contract_envelope_shape(payload)
    assert payload["intent"]["query_intent"] == "page_type_lookup"
    item = payload["results"][0]
    assert_contract_result_shape(item)
    assert item["type"] == "page_context"
    assert item["content"]["page_type"] == "user_preferences"
    assert item["diagnostics"]["matched_on"] == "page_type"


def test_runtime_query_empty_result_contract_keeps_required_lists(tmp_path: Path) -> None:
    dashboard = make_page("0001-my", "https://example.com/my", page_type=PageType.DASHBOARD)
    run_dir = tmp_path / "run"
    write_saved_run(
        run_dir,
        make_manifest("student", [dashboard], workflow_edge_count=0),
        WorkflowGraph(role_profile="student", total_edges=0, edges=[]),
    )

    result = runner.invoke(
        app,
        [
            "runtime-query",
            "--run",
            str(run_dir),
            "--lookup-mode",
            "page",
            "--query",
            "https://example.com/missing",
            "--json-contract",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert_contract_envelope_shape(payload)
    assert payload["results"] == []
    assert payload["intent"]["filters"] == []
