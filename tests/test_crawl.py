from moodle_sitemap.crawl import CrawlVisitIndex


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
