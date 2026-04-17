# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

"""Small, explicit settle strategies for post-navigation page readiness."""

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from moodle_sitemap.models import SettleStrategy


SHORT_SETTLE_MS = 750
ADAPTIVE_SETTLE_MS = 500


def apply_settle_strategy(page: Page, strategy: SettleStrategy) -> None:
    """Apply one conservative settle strategy after DOMContentLoaded navigation."""

    if strategy == SettleStrategy.NETWORKIDLE:
        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except PlaywrightTimeoutError:
            pass
        return

    if strategy == SettleStrategy.DOMCONTENTLOADED:
        return

    if strategy == SettleStrategy.DOMCONTENTLOADED_SHORT_SETTLE:
        page.wait_for_timeout(SHORT_SETTLE_MS)
        return

    if strategy == SettleStrategy.ADAPTIVE:
        try:
            page.wait_for_selector("body", state="attached", timeout=2_000)
        except PlaywrightTimeoutError:
            pass
        try:
            page.wait_for_selector(
                "main, [role='main'], #page, #region-main",
                state="attached",
                timeout=1_000,
            )
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(ADAPTIVE_SETTLE_MS)
        return

    raise ValueError(f"Unsupported settle strategy: {strategy}")
