from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


@dataclass(slots=True)
class BrowserSession:
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page


@contextmanager
def open_browser(headless: bool = True) -> Iterator[BrowserSession]:
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=headless)
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
