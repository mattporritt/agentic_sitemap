from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PageType(StrEnum):
    DASHBOARD = "dashboard"
    COURSE_VIEW = "course_view"
    ACTIVITY_VIEW = "activity_view"
    ADMIN_SETTINGS = "admin_settings"
    USER_PROFILE = "user_profile"
    GRADEBOOK = "gradebook"
    UNKNOWN = "unknown"


class BrowserEngine(StrEnum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"


class FormSummary(StrictModel):
    id: str | None = None
    method: str | None = None
    action: str | None = None
    field_names: list[str] = Field(default_factory=list)


class EditorSummary(StrictModel):
    has_tinymce: bool = False
    has_atto: bool = False
    has_textarea: bool = False


class LabelledElement(StrictModel):
    label: str
    url: str | None = None


class FooterDebugInfo(StrictModel):
    raw_text: str | None = None
    generation_time_seconds: float | None = None
    peak_memory_mb: float | None = None
    included_files: int | None = None
    db_queries: int | None = None
    debug_messages: list[str] = Field(default_factory=list)


class NetworkEvent(StrictModel):
    url: str
    method: str
    resource_type: str | None = None
    status: int | None = None
    content_type: str | None = None


class PageFeatures(StrictModel):
    body_id: str | None = None
    body_classes: list[str] = Field(default_factory=list)
    breadcrumbs: list[str] = Field(default_factory=list)
    forms: list[FormSummary] = Field(default_factory=list)
    editors: EditorSummary = Field(default_factory=EditorSummary)
    links: list[LabelledElement] = Field(default_factory=list)
    buttons: list[LabelledElement] = Field(default_factory=list)


class PageRecord(StrictModel):
    page_id: str
    url: str
    final_url: str
    title: str | None = None
    page_type: PageType = PageType.UNKNOWN
    referrer: str | None = None
    http_status: int | None = None
    features: PageFeatures
    footer: FooterDebugInfo | None = None
    discovered_links: list[str] = Field(default_factory=list)
    network: list[NetworkEvent] = Field(default_factory=list)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SiteManifest(StrictModel):
    site_url: HttpUrl
    origin: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    max_pages: int
    visited_pages: int
    pages: list[PageRecord] = Field(default_factory=list)


class SmokeTestConfig(StrictModel):
    site_url: HttpUrl
    username: str
    password: str
    browser_engine: BrowserEngine = BrowserEngine.CHROMIUM
    headless: bool = True


class SmokeTestRecord(StrictModel):
    configured_site_url: HttpUrl
    browser_engine: BrowserEngine
    initial_url: str
    final_url: str
    page_title: str | None = None
    http_status: int | None = None
    body_id: str | None = None
    body_classes: list[str] = Field(default_factory=list)
    breadcrumbs: list[str] = Field(default_factory=list)
    login_succeeded: bool
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
