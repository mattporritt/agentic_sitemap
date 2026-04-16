# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from typing import TYPE_CHECKING

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

if TYPE_CHECKING:
    from playwright.sync_api import Page, Response


@dataclass(slots=True)
class LoginResult:
    final_url: str
    response_status: int | None = None


def login_appears_successful(page: Page) -> bool:
    if "login" in page.url.lower() and page.locator('input[name="password"], input#password').count() > 0:
        return False
    if page.locator('a[data-title="logout"], a[href*="logout"]').count() > 0:
        return True
    if page.locator("#page, #page-wrapper, body").count() > 0:
        return True
    return False


def login_to_moodle(page: Page, site_url: str, username: str, password: str) -> LoginResult:
    login_url = urljoin(site_url.rstrip("/") + "/", "login/index.php")
    page.goto(login_url, wait_until="domcontentloaded")

    username_selector = 'input[name="username"], input#username'
    password_selector = 'input[name="password"], input#password'
    submit_selector = (
        'button[type="submit"], input[type="submit"], '
        'button[id*="login"], button[name*="login"]'
    )

    page.locator(username_selector).first.fill(username)
    page.locator(password_selector).first.fill(password)

    navigation_response: Response | None = None
    submit = page.locator(submit_selector).first
    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=10_000) as navigation_info:
            if submit.count():
                submit.click()
            else:
                page.locator(password_selector).first.press("Enter")
        navigation_response = navigation_info.value
    except PlaywrightTimeoutError:
        if submit.count():
            submit.click()
        else:
            page.locator(password_selector).first.press("Enter")

    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded")

    if not login_appears_successful(page):
        raise RuntimeError("Login did not appear to complete successfully.")

    return LoginResult(
        final_url=page.url,
        response_status=navigation_response.status if navigation_response else None,
    )
