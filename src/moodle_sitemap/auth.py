from __future__ import annotations

from urllib.parse import urljoin

from typing import TYPE_CHECKING

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

if TYPE_CHECKING:
    from playwright.sync_api import Page


def login_to_moodle(page: Page, site_url: str, username: str, password: str) -> str:
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

    submit = page.locator(submit_selector).first
    if submit.count():
        submit.click()
    else:
        page.locator(password_selector).first.press("Enter")

    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded")

    still_on_login = page.locator(password_selector).count() > 0 and "login" in page.url
    if still_on_login:
        raise RuntimeError("Login did not appear to complete successfully.")

    return page.url
