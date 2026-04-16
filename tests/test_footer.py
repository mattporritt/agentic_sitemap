# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
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
    assert result.current_memory_mb == 8.5
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


def test_parse_footer_text_extracts_current_moodle_performance_footer() -> None:
    footer = (
        "0.134649 secs RAM: 6.8 MB RAM peak: 8.1 MB Included 1084 files "
        "DB reads/writes: 37/0 DB queries time: 0.01035 secs "
        "This page is: General type: mydashboard. Context User: Admin User (context id 5). "
        "Page type my-index."
    )

    result = parse_footer_text(footer)

    assert result is not None
    assert result.raw_text == footer
    assert result.generation_time_seconds == 0.134649
    assert result.current_memory_mb == 6.8
    assert result.peak_memory_mb == 8.1
    assert result.included_files == 1084
    assert result.db_queries is None
    assert result.db_reads == 37
    assert result.db_writes == 0
    assert result.db_queries_time_seconds == 0.01035
    assert result.general_type == "mydashboard"
    assert result.page_type_hint == "my-index"
    assert result.context_summary == "User: Admin User (context id 5)"


def test_parse_footer_text_leaves_unknown_numeric_fields_null() -> None:
    footer = "DB queries time: unknown | Context User: Admin User (context id 5)."

    result = parse_footer_text(footer)

    assert result is not None
    assert result.generation_time_seconds is None
    assert result.current_memory_mb is None
    assert result.peak_memory_mb is None
    assert result.included_files is None
    assert result.db_queries is None
    assert result.db_reads is None
    assert result.db_writes is None
