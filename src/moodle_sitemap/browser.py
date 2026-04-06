from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from moodle_sitemap.models import BrowserEngine


@dataclass(slots=True)
class BrowserSession:
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page


@contextmanager
def open_browser(
    *,
    headless: bool = True,
    engine: BrowserEngine = BrowserEngine.CHROMIUM,
) -> Iterator[BrowserSession]:
    playwright = sync_playwright().start()
    browser_launcher = _get_browser_launcher(playwright, engine)
    browser = browser_launcher.launch(headless=headless)
    context = browser.new_context()
    page = context.new_page()
    session = BrowserSession(
        playwright=playwright,
        browser=browser,
        context=context,
        page=page,
    )
    try:
        yield session
    finally:
        context.close()
        browser.close()
        playwright.stop()


def _get_browser_launcher(playwright: Playwright, engine: BrowserEngine):
    if engine == BrowserEngine.CHROMIUM:
        return playwright.chromium
    if engine == BrowserEngine.FIREFOX:
        return playwright.firefox
    raise ValueError(f"Unsupported browser engine: {engine}")
