from datetime import datetime, timezone
import json
from pathlib import Path

from moodle_sitemap.discovery import (
    build_discovery_summary,
    recommended_next_actions,
    route_family,
    route_signature,
    load_optional_manifest,
)
from moodle_sitemap.models import PageAffordances, PageRecord, PageType, SiteManifest


def make_page(
    page_id: str,
    normalized_url: str,
    *,
    page_type: PageType,
    load_duration_seconds: float = 0.1,
    crawl_depth: int = 0,
) -> PageRecord:
    return PageRecord(
        page_id=page_id,
        url=normalized_url,
        normalized_url=normalized_url,
        final_url=normalized_url,
        title=page_id,
        page_type=page_type,
        body_classes=[],
        breadcrumbs=[],
        discovered_links=[],
        network=[],
        load_duration_seconds=load_duration_seconds,
        crawl_depth=crawl_depth,
    )


def test_route_family_uses_first_two_path_segments() -> None:
    assert route_family("https://example.com/course/view.php?id=4") == "/course/view.php"
    assert route_family("https://example.com/") == "/"


def test_route_signature_groups_by_query_keys() -> None:
    assert route_signature("https://example.com/calendar/view.php?view=month&time=1") == "/calendar/view.php?time,view"


def test_build_discovery_summary_collects_counts_and_candidates(tmp_path: Path) -> None:
    started = datetime(2026, 4, 8, 10, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 4, 8, 10, 1, 0, tzinfo=timezone.utc)
    pages = [
        make_page("0001-my", "https://example.com/my", page_type=PageType.DASHBOARD, load_duration_seconds=0.2),
        make_page(
            "0002-course-view",
            "https://example.com/course/view.php?id=4",
            page_type=PageType.COURSE_VIEW,
            load_duration_seconds=1.5,
            crawl_depth=2,
        ),
        make_page(
            "0003-unknown",
            "https://example.com/custom/page.php?foo=1",
            page_type=PageType.UNKNOWN,
            load_duration_seconds=0.8,
            crawl_depth=3,
        ),
    ]
    manifest = SiteManifest(
        site_url="https://example.com",
        origin="https://example.com",
        crawl_started_at=started,
        crawl_finished_at=finished,
        max_pages=50,
        visited_pages=3,
        summary={
            "total_pages": 3,
            "unknown_pages": 1,
            "page_type_counts": {page_type.value: (1 if page_type in {PageType.DASHBOARD, PageType.COURSE_VIEW, PageType.UNKNOWN} else 0) for page_type in PageType},
            "crawl_started_at": started,
            "crawl_finished_at": finished,
        },
        pages=pages,
    )
    baseline = SiteManifest(
        site_url="https://example.com",
        origin="https://example.com",
        crawl_started_at=started,
        crawl_finished_at=finished,
        max_pages=10,
        visited_pages=1,
        summary={
            "total_pages": 1,
            "unknown_pages": 0,
            "page_type_counts": {page_type.value: (1 if page_type == PageType.DASHBOARD else 0) for page_type in PageType},
            "crawl_started_at": started,
            "crawl_finished_at": finished,
        },
        pages=[pages[0]],
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "workflow-edges.json").write_text(
        json.dumps(
            {
                "edge_type_counts": {"navigation": 1, "related": 1},
                "candidate_edge_count": 3,
                "suppressed_edge_count": 1,
                "deduplicated_pair_count": 1,
                "compressed_edge_count": 2,
                "cluster_count": 1,
                "edge_weight_counts": {"high": 1, "medium": 0, "low": 1},
                "edge_relevance_counts": {"task": 1, "support": 0, "navigation": 0, "contextual": 1},
                "pre_dedup_edge_weight_counts": {"high": 1, "medium": 1, "low": 1},
                "pre_dedup_edge_relevance_counts": {"task": 1, "support": 1, "navigation": 0, "contextual": 1},
                "next_step_changed_pages": [
                    {"page_id": "0002-course-view", "before_targets": ["https://example.com/custom/page.php?foo=1"], "after_targets": ["https://example.com/course/view.php?id=4"]}
                ],
                "background_clusters": [
                    {
                        "cluster_type": "generic_admin_navigation_cluster",
                        "source_page_id": "0002-course-view",
                        "family_key": "/admin/tool",
                        "count": 2,
                        "representative_targets": ["https://example.com/admin/tool/foo/index.php"],
                        "edge_relevance": "contextual",
                        "edge_weight": "low",
                        "reason_hint": "compressed-admin-background-navigation",
                    }
                ],
                "edges": [
                    {"from_page_id": "0002-course-view", "edge_relevance": "task", "edge_weight": "high"},
                    {"from_page_id": "0003-unknown", "edge_relevance": "contextual"},
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = build_discovery_summary(manifest, run_dir=run_dir, baseline_manifest=baseline)

    assert summary.total_pages == 3
    assert summary.unique_normalized_urls == 3
    assert summary.unknown_pages == 1
    assert summary.max_depth_reached == 3
    assert summary.page_type_counts["course_view"] == 1
    assert summary.workflow_candidate_edge_count == 3
    assert summary.workflow_suppressed_edge_count == 1
    assert summary.workflow_deduplicated_pairs == 1
    assert summary.workflow_compressed_edge_count == 2
    assert summary.workflow_cluster_count == 1
    assert summary.workflow_edge_weight_counts["high"] == 1
    assert summary.workflow_edge_relevance_counts["task"] == 1
    assert summary.workflow_pre_dedup_edge_weight_counts["medium"] == 1
    assert summary.top_route_families[0]["route_family"] in {"/course/view.php", "/custom/page.php", "/my"}
    assert summary.query_heavy_routes
    assert summary.slowest_pages[0]["normalized_url"] == "https://example.com/course/view.php?id=4"
    assert summary.unknown_pages_detail[0]["normalized_url"] == "https://example.com/custom/page.php?foo=1"
    assert "/course/view.php" in summary.newly_seen_route_families
    assert summary.top_task_edge_page_types[0]["page_type"] == "course_view"
    assert summary.top_high_value_edge_page_types[0]["page_type"] == "course_view"
    assert summary.top_compressed_route_families[0]["family_key"] == "/admin/tool"
    assert summary.pages_with_most_compression[0]["page_id"] == "0002-course-view"
    assert summary.strongest_primary_pages[0]["page_id"] == "0001-my"
    assert summary.intent_populated_pages == 0
    assert summary.materially_changed_next_steps[0]["page_id"] == "0002-course-view"


def test_recommended_next_actions_returns_human_useful_items() -> None:
    summary = build_discovery_summary(
        SiteManifest(
            site_url="https://example.com",
            origin="https://example.com",
            crawl_started_at=datetime(2026, 4, 8, 10, 0, 0, tzinfo=timezone.utc),
            crawl_finished_at=datetime(2026, 4, 8, 10, 0, 30, tzinfo=timezone.utc),
            max_pages=5,
            visited_pages=1,
            summary={
                "total_pages": 1,
                "unknown_pages": 1,
                "page_type_counts": {page_type.value: (1 if page_type == PageType.UNKNOWN else 0) for page_type in PageType},
                "crawl_started_at": datetime(2026, 4, 8, 10, 0, 0, tzinfo=timezone.utc),
                "crawl_finished_at": datetime(2026, 4, 8, 10, 0, 30, tzinfo=timezone.utc),
            },
            pages=[make_page("0001-unknown", "https://example.com/custom/page.php?foo=1", page_type=PageType.UNKNOWN)],
        ),
        run_dir=Path("discovery-runs/test"),
        baseline_manifest=None,
    )
    actions = recommended_next_actions(summary)
    assert actions


def test_load_optional_manifest_tolerates_legacy_page_fields(tmp_path: Path) -> None:
    manifest_path = tmp_path / "sitemap.json"
    manifest_path.write_text(
        json.dumps(
            {
                "site_url": "https://example.com/",
                "origin": "https://example.com",
                "crawl_started_at": "2026-04-08T10:00:00Z",
                "crawl_finished_at": "2026-04-08T10:00:30Z",
                "max_pages": 5,
                "visited_pages": 1,
                "summary": {
                    "total_pages": 1,
                    "unknown_pages": 0,
                    "page_type_counts": {
                        **{page_type.value: (1 if page_type == PageType.DASHBOARD else 0) for page_type in PageType},
                        "admin_settings": 1,
                    },
                    "crawl_started_at": "2026-04-08T10:00:00Z",
                    "crawl_finished_at": "2026-04-08T10:00:30Z",
                },
                "pages": [
                    {
                        "page_id": "0001-my",
                        "url": "https://example.com/",
                        "normalized_url": "https://example.com/my",
                        "final_url": "https://example.com/my",
                        "title": "Dashboard",
                        "page_type": "admin_settings",
                        "body_id": "page-my-index",
                        "body_classes": ["path-my"],
                        "breadcrumbs": [],
                        "forms": [],
                        "editors": {"has_tinymce": False, "has_atto": False, "has_textarea": True},
                        "links": [],
                        "buttons": [],
                        "discovered_links": [],
                        "network": [],
                        "captured_at": "2026-04-08T10:00:15Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_optional_manifest(manifest_path)

    assert manifest is not None
    assert manifest.pages[0].affordances == PageAffordances()
    assert manifest.pages[0].page_type == PageType.ADMIN_SETTING_PAGE
    assert manifest.summary.page_type_counts["admin_setting_page"] == 1
