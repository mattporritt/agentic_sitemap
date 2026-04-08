from datetime import datetime, timezone
from pathlib import Path

from moodle_sitemap.compare_runs import build_run_comparison_summary
from moodle_sitemap.models import (
    ActionAffordance,
    AffordanceElementType,
    PageAffordances,
    PageRecord,
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
    assert summary.pages_only_in_left == ["https://example.com/course/view.php?id=4"]
    assert summary.pages_only_in_right == ["https://example.com/message/index.php"]
    assert summary.edge_signatures_only_in_left == [
        "navigation:https://example.com/my->https://example.com/course/view.php?id=4"
    ]
    assert summary.affordance_differences[0]["normalized_url"] == "https://example.com/my"
