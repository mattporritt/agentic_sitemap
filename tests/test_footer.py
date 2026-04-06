from moodle_sitemap.extract.footer import parse_footer_text


def test_parse_footer_text_extracts_metrics() -> None:
    footer = (
        "Page generated in 0.123 seconds | 4 DB queries | "
        "12 included files | 8.5 MB memory"
    )

    result = parse_footer_text(footer)

    assert result is not None
    assert result.generation_time_seconds == 0.123
    assert result.db_queries == 4
    assert result.included_files == 12
    assert result.peak_memory_mb == 8.5


def test_parse_footer_text_collects_debug_fragments() -> None:
    footer = "Debug: developer debugging enabled | Warning: missing capability check"

    result = parse_footer_text(footer)

    assert result is not None
    assert result.debug_messages == [
        "Debug: developer debugging enabled",
        "Warning: missing capability check",
    ]


def test_parse_footer_text_returns_none_for_blank_values() -> None:
    assert parse_footer_text("") is None
