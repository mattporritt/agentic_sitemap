from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from moodle_sitemap.models import FooterDebugInfo

GENERATION_PATTERN = re.compile(r"page generated in\s+([0-9]+(?:\.[0-9]+)?)\s+seconds?", re.IGNORECASE)
MEMORY_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*mb memory", re.IGNORECASE)
FILES_PATTERN = re.compile(r"([0-9]+)\s+included files", re.IGNORECASE)
DB_PATTERN = re.compile(r"([0-9]+)\s+db queries", re.IGNORECASE)


def parse_footer_text(text: str | None) -> FooterDebugInfo | None:
    if not text:
        return None

    normalized = " ".join(text.split())
    if not normalized:
        return None

    generation = GENERATION_PATTERN.search(normalized)
    memory = MEMORY_PATTERN.search(normalized)
    files = FILES_PATTERN.search(normalized)
    db = DB_PATTERN.search(normalized)

    debug_messages: list[str] = []
    for fragment in re.split(r"\s*\|\s*|\s{2,}", normalized):
        lowered = fragment.lower()
        if "debug" in lowered or "warning" in lowered or "notice" in lowered:
            debug_messages.append(fragment.strip())

    return FooterDebugInfo(
        raw_text=normalized,
        generation_time_seconds=float(generation.group(1)) if generation else None,
        peak_memory_mb=float(memory.group(1)) if memory else None,
        included_files=int(files.group(1)) if files else None,
        db_queries=int(db.group(1)) if db else None,
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
