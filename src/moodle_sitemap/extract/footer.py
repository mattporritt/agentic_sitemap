# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from moodle_sitemap.models import FooterDebugInfo

GENERATION_PATTERNS = [
    re.compile(r"page generated in\s+([0-9]+(?:\.[0-9]+)?)\s+seconds?", re.IGNORECASE),
    re.compile(r"(^|\s)([0-9]+(?:\.[0-9]+)?)\s+secs\b", re.IGNORECASE),
]
CURRENT_MEMORY_PATTERN = re.compile(r"\bram:\s*([0-9]+(?:\.[0-9]+)?)\s*mb\b", re.IGNORECASE)
PEAK_MEMORY_PATTERN = re.compile(r"\bram peak:\s*([0-9]+(?:\.[0-9]+)?)\s*mb\b", re.IGNORECASE)
LEGACY_MEMORY_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*mb memory\b", re.IGNORECASE)
FILES_PATTERNS = [
    re.compile(r"([0-9]+)\s+included files\b", re.IGNORECASE),
    re.compile(r"\bincluded\s+([0-9]+)\s+files\b", re.IGNORECASE),
]
DB_QUERY_COUNT_PATTERN = re.compile(r"(?<!/)\b([0-9]+)\s+db queries\b", re.IGNORECASE)
DB_READS_WRITES_PATTERN = re.compile(r"\bdb reads/writes:\s*([0-9]+)\s*/\s*([0-9]+)\b", re.IGNORECASE)
DB_QUERIES_TIME_PATTERN = re.compile(r"\bdb queries time:\s*([0-9]+(?:\.[0-9]+)?)\s+secs\b", re.IGNORECASE)
GENERAL_TYPE_PATTERN = re.compile(r"\bgeneral type:\s*([a-z0-9_-]+)\b", re.IGNORECASE)
PAGE_TYPE_PATTERN = re.compile(r"\bpage type\s+([a-z0-9_-]+)\b", re.IGNORECASE)
CONTEXT_PATTERN = re.compile(
    r"\bcontext\s+(.+?)(?:\.\s+(?:page type|purge all caches|reactive instances)\b|$)",
    re.IGNORECASE,
)
THEME_PATTERN = re.compile(r"\btheme:\s*([a-z0-9_-]+)\b", re.IGNORECASE)


def parse_footer_text(text: str | None) -> FooterDebugInfo | None:
    if not text:
        return None

    normalized = " ".join(text.split())
    if not normalized:
        return None

    generation_time = _extract_generation_time(normalized)
    current_memory = _extract_first_float(CURRENT_MEMORY_PATTERN, normalized)
    peak_memory = _extract_first_float(PEAK_MEMORY_PATTERN, normalized)
    legacy_memory = _extract_first_float(LEGACY_MEMORY_PATTERN, normalized)
    included_files = _extract_first_int(FILES_PATTERNS, normalized)
    db_queries = _extract_first_int([DB_QUERY_COUNT_PATTERN], normalized)
    db_reads_writes = DB_READS_WRITES_PATTERN.search(normalized)
    db_queries_time = _extract_first_float(DB_QUERIES_TIME_PATTERN, normalized)
    general_type = _extract_first_text(GENERAL_TYPE_PATTERN, normalized)
    page_type_hint = _extract_first_text(PAGE_TYPE_PATTERN, normalized)
    context_summary = _extract_first_text(CONTEXT_PATTERN, normalized)
    theme_hint = _extract_first_text(THEME_PATTERN, normalized)

    debug_messages: list[str] = []
    for fragment in re.split(r"\s*\|\s*|\s{2,}", normalized):
        lowered = fragment.lower()
        if "debug" in lowered or "warning" in lowered or "notice" in lowered:
            debug_messages.append(fragment.strip())

    return FooterDebugInfo(
        raw_text=normalized,
        generation_time_seconds=generation_time,
        current_memory_mb=current_memory or legacy_memory,
        peak_memory_mb=peak_memory if peak_memory is not None else legacy_memory,
        included_files=included_files,
        db_queries=db_queries,
        db_reads=int(db_reads_writes.group(1)) if db_reads_writes else None,
        db_writes=int(db_reads_writes.group(2)) if db_reads_writes else None,
        db_queries_time_seconds=db_queries_time,
        general_type=general_type,
        page_type_hint=page_type_hint,
        context_summary=context_summary,
        theme_hint=theme_hint,
        debug_messages=debug_messages,
    )


def extract_footer_info(page: Page) -> FooterDebugInfo | None:
    footer_text = page.evaluate(
        """
        () => {
          const footer = document.querySelector("#page-footer, footer");
          return footer ? (footer.innerText || footer.textContent || "") : "";
        }
        """
    )
    return parse_footer_text(footer_text)


def _extract_generation_time(text: str) -> float | None:
    for pattern in GENERATION_PATTERNS:
        match = pattern.search(text)
        if match:
            number = match.group(2) if match.lastindex and match.lastindex > 1 else match.group(1)
            return float(number)
    return None


def _extract_first_float(pattern: re.Pattern[str], text: str) -> float | None:
    match = pattern.search(text)
    return float(match.group(1)) if match else None


def _extract_first_int(patterns: list[re.Pattern[str]], text: str) -> int | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return int(match.group(1))
    return None


def _extract_first_text(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1).strip() if match else None
