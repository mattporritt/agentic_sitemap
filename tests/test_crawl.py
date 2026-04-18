# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from moodle_sitemap.crawl import (
    CrawlVisitIndex,
    format_progress_line,
    is_download_navigation_error,
    is_navigation_timeout_error,
)
from moodle_sitemap.models import PageRecord, PageType


def test_crawl_visit_index_prevents_duplicate_dashboard_after_root_redirect() -> None:
    index = CrawlVisitIndex()
    assert index.mark_queued("https://example.com/")
    index.mark_dequeued("https://example.com/")

    is_new_page = index.mark_visited("https://example.com/", "https://example.com/my")
    assert is_new_page is True

    assert index.mark_queued("https://example.com/my") is False
    assert index.mark_queued("https://example.com/my/") is True
    index.mark_dequeued("https://example.com/my/")
    is_new_page = index.mark_visited("https://example.com/my/", "https://example.com/my")
    assert is_new_page is False


def test_crawl_visit_index_allows_distinct_normalized_urls() -> None:
    index = CrawlVisitIndex()
    assert index.mark_visited("https://example.com/my", "https://example.com/my") is True
    assert index.mark_queued("https://example.com/admin/search.php") is True


def test_format_progress_line_includes_count_page_id_type_and_url() -> None:
    page = PageRecord(
        page_id="0016-course-view-php-id-4",
        url="https://example.com/course/view.php?id=4",
        normalized_url="https://example.com/course/view.php?id=4",
        final_url="https://example.com/course/view.php?id=4",
        title="Course",
        page_type=PageType.COURSE_VIEW,
        body_classes=[],
        breadcrumbs=[],
        discovered_links=[],
        network=[],
    )

    line = format_progress_line(page, current_count=16, max_pages=40)

    assert line == (
        "[16/40] 0016-course-view-php-id-4 "
        "course_view "
        "https://example.com/course/view.php?id=4"
    )


def test_is_download_navigation_error_matches_playwright_download_message() -> None:
    assert is_download_navigation_error(Exception("Page.goto: Download is starting"))
    assert not is_download_navigation_error(Exception("Page.goto: Timeout 30000ms exceeded"))


def test_is_navigation_timeout_error_matches_playwright_timeout_message() -> None:
    assert is_navigation_timeout_error(Exception("Page.goto: Timeout 30000ms exceeded"))
    assert not is_navigation_timeout_error(Exception("Page.goto: Download is starting"))
