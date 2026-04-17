# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

from moodle_sitemap.models import SettleStrategy
from moodle_sitemap.settle import ADAPTIVE_SETTLE_MS, SHORT_SETTLE_MS, apply_settle_strategy


class StubPage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def wait_for_load_state(self, *args: object, **kwargs: object) -> None:
        self.calls.append(("wait_for_load_state", args, kwargs))

    def wait_for_timeout(self, *args: object, **kwargs: object) -> None:
        self.calls.append(("wait_for_timeout", args, kwargs))

    def wait_for_selector(self, *args: object, **kwargs: object) -> None:
        self.calls.append(("wait_for_selector", args, kwargs))


def test_apply_settle_strategy_networkidle_waits_for_load_state() -> None:
    page = StubPage()

    apply_settle_strategy(page, SettleStrategy.NETWORKIDLE)

    assert page.calls == [("wait_for_load_state", ("networkidle",), {"timeout": 5_000})]


def test_apply_settle_strategy_domcontentloaded_does_not_wait() -> None:
    page = StubPage()

    apply_settle_strategy(page, SettleStrategy.DOMCONTENTLOADED)

    assert page.calls == []


def test_apply_settle_strategy_short_settle_waits_fixed_duration() -> None:
    page = StubPage()

    apply_settle_strategy(page, SettleStrategy.DOMCONTENTLOADED_SHORT_SETTLE)

    assert page.calls == [("wait_for_timeout", (SHORT_SETTLE_MS,), {})]


def test_apply_settle_strategy_adaptive_waits_for_body_main_and_short_timeout() -> None:
    page = StubPage()

    apply_settle_strategy(page, SettleStrategy.ADAPTIVE)

    assert page.calls == [
        ("wait_for_selector", ("body",), {"state": "attached", "timeout": 2_000}),
        (
            "wait_for_selector",
            ("main, [role='main'], #page, #region-main",),
            {"state": "attached", "timeout": 1_000},
        ),
        ("wait_for_timeout", (ADAPTIVE_SETTLE_MS,), {}),
    ]
