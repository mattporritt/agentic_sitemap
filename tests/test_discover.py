from moodle_sitemap.discover import canonicalize_resolved_url, filter_discovered_links, normalize_url


def test_normalize_url_removes_fragment_and_tracking_query() -> None:
    result = normalize_url(
        "https://example.com/course/view.php?id=2&utm_source=newsletter#section-1"
    )
    assert result == "https://example.com/course/view.php?id=2"


def test_normalize_url_sorts_query_parameters() -> None:
    result = normalize_url("https://example.com/mod/forum/view.php?b=2&a=1")
    assert result == "https://example.com/mod/forum/view.php?a=1&b=2"


def test_filter_discovered_links_keeps_same_origin_safe_unique_links() -> None:
    links = [
        "/course/view.php?id=2",
        "https://example.com/course/view.php?id=2#intro",
        "mailto:test@example.com",
        "/login/logout.php?sesskey=abc",
        "https://other.example.com/course/view.php?id=9",
    ]

    result = filter_discovered_links(
        links,
        base_url="https://example.com/my/",
        origin="https://example.com",
    )

    assert result == ["https://example.com/course/view.php?id=2"]


def test_normalize_url_removes_trailing_slash_for_non_root() -> None:
    assert normalize_url("https://example.com/my/") == "https://example.com/my"


def test_canonicalize_resolved_url_prefers_resolved_destination() -> None:
    result = canonicalize_resolved_url("https://example.com/", "https://example.com/my/")
    assert result == "https://example.com/my"
