from datetime import datetime, timezone

from moodle_sitemap.auth import LoginResult
from moodle_sitemap.crawl import build_manifest_summary
from moodle_sitemap.models import (
    ActionAffordance,
    AffordanceElementType,
    BrowserEngine,
    NextStepHint,
    PageRiskLevel,
    PageSafetySummary,
    PageFeatures,
    PageAffordances,
    PageRecord,
    PageType,
    SafetyHints,
    SmokeTestConfig,
)
from moodle_sitemap.smoke import build_smoke_test_record


def test_build_smoke_test_record_populates_known_fields() -> None:
    config = SmokeTestConfig(
        site_url="https://example.com",
        username="admin",
        password="secret",
        browser_engine=BrowserEngine.FIREFOX,
        headless=True,
    )
    features = PageFeatures(
        body_id="page-my-index",
        body_classes=["path-my", "theme"],
        breadcrumbs=["Dashboard"],
    )

    record = build_smoke_test_record(
        config=config,
        login_result=LoginResult(final_url="https://example.com/my", response_status=200),
        page_title="Dashboard | Moodle Demo",
        features=features,
        login_succeeded=True,
    )

    assert str(record.site_url) == "https://example.com/"
    assert record.role_profile == "unlabeled"
    assert record.browser == BrowserEngine.FIREFOX
    assert record.initial_url == "https://example.com/"
    assert record.final_url == "https://example.com/my"
    assert record.page_title == "Dashboard | Moodle Demo"
    assert record.http_status == 200
    assert record.body_id == "page-my-index"
    assert record.body_classes == ["path-my", "theme"]
    assert record.breadcrumbs == ["Dashboard"]
    assert record.login_succeeded is True


def test_page_record_serializes_flat_schema_fields() -> None:
    page = PageRecord(
        page_id="0001-my",
        url="https://example.com/",
        normalized_url="https://example.com/my",
        final_url="https://example.com/my",
        title="Dashboard | Moodle Demo",
        page_type=PageType.DASHBOARD,
        http_status=200,
        body_id="page-my-index",
        body_classes=["path-my", "theme"],
        breadcrumbs=["Dashboard"],
        affordances=PageAffordances(
            actions=[
                ActionAffordance(
                    label="Turn editing on",
                    element_type=AffordanceElementType.BUTTON,
                    action_key="turn-editing-on",
                    safety=SafetyHints(likely_mutating=True),
                )
            ]
        ),
        safety=PageSafetySummary(page_risk_level=PageRiskLevel.MEDIUM, contains_mutating_actions=True),
        discovered_links=[],
        network=[],
    )

    dumped = page.model_dump()

    assert dumped["page_id"] == "0001-my"
    assert dumped["body_id"] == "page-my-index"
    assert dumped["body_classes"] == ["path-my", "theme"]
    assert dumped["breadcrumbs"] == ["Dashboard"]
    assert dumped["affordances"]["actions"][0]["action_key"] == "turn-editing-on"
    assert dumped["safety"]["page_risk_level"] == "medium"
    assert dumped["next_steps"] == []
    assert "features" not in dumped


def test_build_manifest_summary_counts_page_types() -> None:
    started = datetime(2026, 4, 7, 10, 15, 30, tzinfo=timezone.utc)
    ended = datetime(2026, 4, 7, 10, 16, 0, tzinfo=timezone.utc)
    pages = [
        PageRecord(
            page_id="0001-my",
            url="https://example.com/",
            normalized_url="https://example.com/my",
            final_url="https://example.com/my",
            title="Dashboard",
            page_type=PageType.DASHBOARD,
            body_classes=[],
            breadcrumbs=[],
            discovered_links=[],
            network=[],
        ),
        PageRecord(
            page_id="0002-admin-search",
            url="https://example.com/admin/search.php",
            normalized_url="https://example.com/admin/search.php",
            final_url="https://example.com/admin/search.php",
            title="Admin",
            page_type=PageType.ADMIN_SETTINGS,
            body_classes=[],
            breadcrumbs=[],
            discovered_links=[],
            network=[],
        ),
        PageRecord(
            page_id="0003-unknown",
            url="https://example.com/message",
            normalized_url="https://example.com/message",
            final_url="https://example.com/message",
            title="Message",
            page_type=PageType.UNKNOWN,
            body_classes=[],
            breadcrumbs=[],
            discovered_links=[],
            network=[],
        ),
    ]

    summary = build_manifest_summary(pages, crawl_started_at=started, crawl_finished_at=ended)

    assert summary.total_pages == 3
    assert summary.unknown_pages == 1
    assert summary.workflow_edge_count == 0
    assert summary.page_type_counts["dashboard"] == 1
    assert summary.page_type_counts["admin_settings"] == 1
    assert summary.page_type_counts["course_switch_role"] == 0
    assert summary.page_type_counts["contact_site_support"] == 0
    assert summary.page_type_counts["messages"] == 0
    assert summary.page_type_counts["unknown"] == 1
    assert summary.page_type_counts["calendar"] == 0
    assert summary.crawl_started_at == started
    assert summary.crawl_finished_at == ended


def test_page_record_serializes_next_steps() -> None:
    page = PageRecord(
        page_id="0001-my",
        url="https://example.com/my",
        normalized_url="https://example.com/my",
        final_url="https://example.com/my",
        title="Dashboard",
        page_type=PageType.DASHBOARD,
        body_classes=[],
        breadcrumbs=[],
        next_steps=[
            NextStepHint(
                page_id="0002-course",
                target_url="https://example.com/course/view.php?id=4",
                edge_type="navigation",
                label="Course 1",
                confidence=0.95,
                notes="dashboard-to-course",
            )
        ],
        discovered_links=[],
        network=[],
    )

    dumped = page.model_dump()

    assert dumped["next_steps"][0]["edge_type"] == "navigation"
    assert dumped["next_steps"][0]["page_id"] == "0002-course"
