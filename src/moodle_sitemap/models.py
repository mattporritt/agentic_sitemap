# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

"""Shared artifact models and enums for `moodle-sitemap`.

The models in this file define the saved JSON contract. Downstream workflows,
comparison logic, and task validation all depend on these types staying
internally consistent.
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class StrictModel(BaseModel):
    """Base model that forbids undeclared fields in saved artifacts."""

    model_config = ConfigDict(extra="forbid")


class PageType(StrEnum):
    DASHBOARD = "dashboard"
    COURSE_VIEW = "course_view"
    COURSE_EDIT = "course_edit"
    COURSE_SWITCH_ROLE = "course_switch_role"
    ACTIVITY_VIEW = "activity_view"
    ACTIVITY_EDIT = "activity_edit"
    ADMIN_SEARCH = "admin_search"
    ADMIN_CATEGORY = "admin_category"
    ADMIN_SETTING_PAGE = "admin_setting_page"
    ADMIN_TOOL_PAGE = "admin_tool_page"
    CONTACT_SITE_SUPPORT = "contact_site_support"
    USER_PROFILE = "user_profile"
    USER_PROFILE_EDIT = "user_profile_edit"
    USER_PREFERENCES = "user_preferences"
    USER_SETTINGS_PAGE = "user_settings_page"
    PRIVATE_FILES = "private_files"
    CONTENT_BANK_PREFERENCES = "content_bank_preferences"
    MESSAGES = "messages"
    MESSAGE_PREFERENCES = "message_preferences"
    NOTIFICATIONS = "notifications"
    CALENDAR = "calendar"
    BLOG_PAGE = "blog_page"
    FORUM_USER_PAGE = "forum_user_page"
    REPORT_BUILDER = "report_builder"
    GRADEBOOK = "gradebook"
    UNKNOWN = "unknown"


class BrowserEngine(StrEnum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"


class AffordanceElementType(StrEnum):
    LINK = "link"
    BUTTON = "button"
    SUBMIT = "submit"
    MENU_TRIGGER = "menu_trigger"
    TAB = "tab"


class FormFieldType(StrEnum):
    TEXT = "text"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    HIDDEN = "hidden"
    FILE = "file"
    OTHER = "other"


class FormPurpose(StrEnum):
    SEARCH_FORM = "search_form"
    FILTER_FORM = "filter_form"
    EDIT_FORM = "edit_form"
    SETTINGS_FORM = "settings_form"
    MESSAGE_FORM = "message_form"
    UPLOAD_FORM = "upload_form"
    UNKNOWN_FORM = "unknown_form"


class FilterControlPurpose(StrEnum):
    SEARCH = "search"
    FILTER = "filter"
    SORT = "sort"
    UNKNOWN = "unknown"


class ImportanceLevel(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"


class LikelyIntent(StrEnum):
    CREATE = "create"
    EDIT = "edit"
    SAVE = "save"
    DELETE = "delete"
    SEARCH = "search"
    FILTER = "filter"
    NAVIGATE = "navigate"
    CONFIGURE = "configure"
    MESSAGE = "message"
    REPORT = "report"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    VIEW = "view"
    UNKNOWN = "unknown"


class MutationStrength(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkflowEdgeType(StrEnum):
    NAVIGATION = "navigation"
    PARENT_CHILD = "parent_child"
    SETTINGS = "settings"
    EDIT = "edit"
    PREFERENCES = "preferences"
    ACTIVITY = "activity"
    ADMIN = "admin"
    RELATED = "related"


class PageRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EdgeWeight(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EdgeRelevance(StrEnum):
    TASK = "task"
    SUPPORT = "support"
    NAVIGATION = "navigation"
    CONTEXTUAL = "contextual"


class SafetyHints(StrictModel):
    inspect_only: bool = False
    navigation_safe: bool = False
    likely_mutating: bool = False
    likely_destructive: bool = False
    requires_confirmation_likely: bool = False


class PageSafetySummary(StrictModel):
    page_risk_level: PageRiskLevel = PageRiskLevel.LOW
    contains_mutating_actions: bool = False
    contains_destructive_actions: bool = False
    likely_requires_confirmation: bool = False
    contains_sesskey_backed_actions: bool = False
    navigation_safe_action_count: int = 0
    mutating_action_count: int = 0


class ActionAffordance(StrictModel):
    label: str
    url: str | None = None
    element_type: AffordanceElementType = AffordanceElementType.LINK
    action_key: str | None = None
    importance_level: ImportanceLevel = ImportanceLevel.TERTIARY
    likely_intent: LikelyIntent = LikelyIntent.UNKNOWN
    prominence_score: int = 0
    in_primary_region: bool = False
    in_menu_or_overflow: bool = False
    is_primary: bool = False
    disabled: bool = False
    safety: SafetyHints = Field(default_factory=SafetyHints)


class FormFieldAffordance(StrictModel):
    name: str | None = None
    label: str | None = None
    field_type: FormFieldType = FormFieldType.OTHER
    visible: bool = True
    required: bool = False


class FormAffordance(StrictModel):
    id: str | None = None
    method: str | None = None
    action: str | None = None
    fields: list[FormFieldAffordance] = Field(default_factory=list)
    submit_controls: list[ActionAffordance] = Field(default_factory=list)
    purpose: FormPurpose = FormPurpose.UNKNOWN_FORM
    importance_level: ImportanceLevel = ImportanceLevel.TERTIARY
    likely_intent: LikelyIntent = LikelyIntent.UNKNOWN
    likely_mutation_strength: MutationStrength = MutationStrength.NONE
    central_to_page: bool = False
    safety: SafetyHints = Field(default_factory=SafetyHints)


class EditorSummary(StrictModel):
    has_tinymce: bool = False
    has_atto: bool = False
    has_textarea: bool = False


class NavigationItem(StrictModel):
    label: str
    url: str | None = None
    kind: str | None = None
    current: bool = False
    importance_level: ImportanceLevel = ImportanceLevel.TERTIARY
    likely_intent: LikelyIntent = LikelyIntent.NAVIGATE


class TabAffordance(StrictModel):
    label: str
    url: str | None = None
    current: bool = False


class FileInputAffordance(StrictModel):
    name: str | None = None
    label: str | None = None
    accept: str | None = None
    multiple: bool = False


class FilterControlAffordance(StrictModel):
    name: str | None = None
    label: str | None = None
    control_type: FormFieldType = FormFieldType.OTHER
    purpose: FilterControlPurpose = FilterControlPurpose.UNKNOWN


class TableAffordance(StrictModel):
    region_label: str | None = None
    column_headers: list[str] = Field(default_factory=list)
    row_count: int = 0


class ListRegionAffordance(StrictModel):
    region_label: str | None = None
    item_count: int = 0
    list_type: str | None = None


class SectionAffordance(StrictModel):
    label: str
    kind: str | None = None


class PageAffordances(StrictModel):
    actions: list[ActionAffordance] = Field(default_factory=list)
    navigation: list[NavigationItem] = Field(default_factory=list)
    forms: list[FormAffordance] = Field(default_factory=list)
    editors: EditorSummary = Field(default_factory=EditorSummary)
    file_inputs: list[FileInputAffordance] = Field(default_factory=list)
    filters: list[FilterControlAffordance] = Field(default_factory=list)
    tabs: list[TabAffordance] = Field(default_factory=list)
    tables: list[TableAffordance] = Field(default_factory=list)
    lists: list[ListRegionAffordance] = Field(default_factory=list)
    sections: list[SectionAffordance] = Field(default_factory=list)


class PageTaskSummary(StrictModel):
    primary_page_intent: LikelyIntent = LikelyIntent.UNKNOWN
    primary_actions: list[str] = Field(default_factory=list)
    task_relevance_score: int = 0


class WorkflowEdge(StrictModel):
    from_page_id: str
    to_page_id: str | None = None
    target_url: str
    target_page_type: PageType | None = None
    edge_type: WorkflowEdgeType = WorkflowEdgeType.RELATED
    source_affordance_label: str | None = None
    source_affordance_kind: str | None = None
    source_affordance_importance: ImportanceLevel | None = None
    edge_weight: EdgeWeight = EdgeWeight.LOW
    edge_relevance: EdgeRelevance = EdgeRelevance.CONTEXTUAL
    confidence: float | None = None
    reason_hint: str | None = None
    notes: str | None = None


class BackgroundNavigationCluster(StrictModel):
    cluster_type: str
    source_page_id: str
    family_key: str
    count: int = 0
    representative_targets: list[str] = Field(default_factory=list)
    edge_relevance: EdgeRelevance = EdgeRelevance.CONTEXTUAL
    edge_weight: EdgeWeight = EdgeWeight.LOW
    reason_hint: str | None = None


class NextStepHint(StrictModel):
    page_id: str | None = None
    target_url: str
    target_page_type: PageType | None = None
    edge_type: WorkflowEdgeType = WorkflowEdgeType.RELATED
    edge_weight: EdgeWeight = EdgeWeight.LOW
    edge_relevance: EdgeRelevance = EdgeRelevance.CONTEXTUAL
    label: str | None = None
    confidence: float | None = None
    likely_intent: LikelyIntent = LikelyIntent.UNKNOWN
    notes: str | None = None


class WorkflowGraph(StrictModel):
    role_profile: str = "unlabeled"
    candidate_edge_count: int = 0
    suppressed_edge_count: int = 0
    deduplicated_pair_count: int = 0
    compressed_edge_count: int = 0
    cluster_count: int = 0
    total_edges: int = 0
    edge_type_counts: dict[str, int] = Field(default_factory=dict)
    edge_weight_counts: dict[str, int] = Field(default_factory=dict)
    edge_relevance_counts: dict[str, int] = Field(default_factory=dict)
    pre_dedup_edge_weight_counts: dict[str, int] = Field(default_factory=dict)
    pre_dedup_edge_relevance_counts: dict[str, int] = Field(default_factory=dict)
    next_step_changed_pages: list[dict[str, object]] = Field(default_factory=list)
    background_clusters: list[BackgroundNavigationCluster] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


class FooterDebugInfo(StrictModel):
    raw_text: str | None = None
    generation_time_seconds: float | None = None
    current_memory_mb: float | None = None
    peak_memory_mb: float | None = None
    included_files: int | None = None
    db_queries: int | None = None
    db_reads: int | None = None
    db_writes: int | None = None
    db_queries_time_seconds: float | None = None
    general_type: str | None = None
    page_type_hint: str | None = None
    context_summary: str | None = None
    theme_hint: str | None = None
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
    affordances: PageAffordances = Field(default_factory=PageAffordances)
    task_summary: PageTaskSummary = Field(default_factory=PageTaskSummary)


class PageRecord(StrictModel):
    page_id: str
    url: str
    normalized_url: str
    final_url: str
    title: str | None = None
    page_type: PageType = PageType.UNKNOWN
    referrer: str | None = None
    http_status: int | None = None
    body_id: str | None = None
    body_classes: list[str] = Field(default_factory=list)
    breadcrumbs: list[str] = Field(default_factory=list)
    affordances: PageAffordances = Field(default_factory=PageAffordances)
    task_summary: PageTaskSummary = Field(default_factory=PageTaskSummary)
    primary_page_intent: LikelyIntent = LikelyIntent.UNKNOWN
    primary_actions: list[str] = Field(default_factory=list)
    task_relevance_score: int = 0
    safety: PageSafetySummary = Field(default_factory=PageSafetySummary)
    next_steps: list[NextStepHint] = Field(default_factory=list)
    background_navigation_clusters: list[BackgroundNavigationCluster] = Field(default_factory=list)
    footer: FooterDebugInfo | None = None
    discovered_links: list[str] = Field(default_factory=list)
    network: list[NetworkEvent] = Field(default_factory=list)
    crawl_depth: int = 0
    load_duration_seconds: float | None = None
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ManifestSummary(StrictModel):
    total_pages: int
    unknown_pages: int
    workflow_edge_count: int = 0
    page_type_counts: dict[str, int] = Field(default_factory=dict)
    crawl_started_at: datetime
    crawl_finished_at: datetime


class DiscoverySummary(StrictModel):
    site_url: HttpUrl
    role_profile: str = "unlabeled"
    run_dir: str
    total_pages: int
    unique_normalized_urls: int
    unknown_pages: int
    workflow_edge_count: int = 0
    workflow_candidate_edge_count: int = 0
    workflow_suppressed_edge_count: int = 0
    workflow_deduplicated_pairs: int = 0
    workflow_compressed_edge_count: int = 0
    workflow_cluster_count: int = 0
    workflow_edge_type_counts: dict[str, int] = Field(default_factory=dict)
    workflow_edge_weight_counts: dict[str, int] = Field(default_factory=dict)
    workflow_edge_relevance_counts: dict[str, int] = Field(default_factory=dict)
    workflow_pre_dedup_edge_weight_counts: dict[str, int] = Field(default_factory=dict)
    workflow_pre_dedup_edge_relevance_counts: dict[str, int] = Field(default_factory=dict)
    crawl_duration_seconds: float
    max_depth_reached: int
    page_type_counts: dict[str, int] = Field(default_factory=dict)
    top_route_families: list[dict[str, int | str]] = Field(default_factory=list)
    query_heavy_routes: list[dict[str, int | str]] = Field(default_factory=list)
    canonicalization_events: int = 0
    slowest_pages: list[dict[str, int | float | str]] = Field(default_factory=list)
    unknown_pages_detail: list[dict[str, str]] = Field(default_factory=list)
    weak_classification_candidates: list[dict[str, str]] = Field(default_factory=list)
    exclusion_candidates: list[dict[str, int | str]] = Field(default_factory=list)
    newly_seen_route_families: list[str] = Field(default_factory=list)
    top_task_edge_page_types: list[dict[str, int | str]] = Field(default_factory=list)
    top_high_value_edge_page_types: list[dict[str, int | str]] = Field(default_factory=list)
    noisy_admin_route_families: list[dict[str, int | str]] = Field(default_factory=list)
    top_compressed_route_families: list[dict[str, int | str]] = Field(default_factory=list)
    pages_with_most_compression: list[dict[str, int | str]] = Field(default_factory=list)
    strongest_primary_pages: list[dict[str, int | str]] = Field(default_factory=list)
    intent_populated_pages: int = 0
    materially_changed_next_steps: list[dict[str, object]] = Field(default_factory=list)


class SiteManifest(StrictModel):
    site_url: HttpUrl
    role_profile: str = "unlabeled"
    origin: str
    crawl_started_at: datetime
    crawl_finished_at: datetime
    max_pages: int
    visited_pages: int
    summary: ManifestSummary
    pages: list[PageRecord] = Field(default_factory=list)


class SmokeTestConfig(StrictModel):
    site_url: HttpUrl
    username: str
    password: str
    role_profile: str = "unlabeled"
    browser_engine: BrowserEngine = BrowserEngine.CHROMIUM
    headless: bool = True


class SmokeTestRecord(StrictModel):
    site_url: HttpUrl
    role_profile: str = "unlabeled"
    browser: BrowserEngine
    initial_url: str
    final_url: str
    page_title: str | None = None
    http_status: int | None = None
    body_id: str | None = None
    body_classes: list[str] = Field(default_factory=list)
    breadcrumbs: list[str] = Field(default_factory=list)
    login_succeeded: bool
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunComparisonSummary(StrictModel):
    left_run_dir: str
    right_run_dir: str
    left_role_profile: str
    right_role_profile: str
    left_total_pages: int
    right_total_pages: int
    shared_page_count: int = 0
    left_workflow_edges: int = 0
    right_workflow_edges: int = 0
    left_task_edges: int = 0
    right_task_edges: int = 0
    page_type_count_deltas: dict[str, dict[str, int]] = Field(default_factory=dict)
    pages_only_in_left: list[str] = Field(default_factory=list)
    pages_only_in_right: list[str] = Field(default_factory=list)
    edge_signatures_only_in_left: list[str] = Field(default_factory=list)
    edge_signatures_only_in_right: list[str] = Field(default_factory=list)
    affordance_differences: list[dict[str, object]] = Field(default_factory=list)
    next_step_differences: list[dict[str, object]] = Field(default_factory=list)
    safety_differences: list[dict[str, object]] = Field(default_factory=list)


class TaskValidationStatus(StrEnum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


class TaskSpec(StrictModel):
    task_id: str
    role_profile: str
    starting_page_type: PageType | None = None
    starting_url_contains: str | None = None
    target_page_type: PageType | None = None
    target_route_family: str | None = None
    target_url_contains: list[str] = Field(default_factory=list)
    expected_intermediate_page_types: list[PageType] = Field(default_factory=list)
    required_affordance_intents: list[LikelyIntent] = Field(default_factory=list)
    success_hint: str


class TaskSpecList(StrictModel):
    tasks: list[TaskSpec] = Field(default_factory=list)


class TaskValidationTaskResult(StrictModel):
    task_id: str
    role_profile: str
    status: TaskValidationStatus
    starting_page_id: str | None = None
    target_page_ids: list[str] = Field(default_factory=list)
    candidate_path_page_ids: list[str] = Field(default_factory=list)
    candidate_path_urls: list[str] = Field(default_factory=list)
    candidate_path_page_types: list[str] = Field(default_factory=list)
    path_length: int | None = None
    path_quality_score: int = 0
    best_path_confidence: int = 0
    first_hop_quality: int = 0
    next_step_support_score: int = 0
    affordance_support_score: int = 0
    key_affordance_relevance: int = 0
    next_steps_helpful: bool = False
    discovered_target: bool = False
    key_affordances: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    target_page_types: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


class TaskValidationSummary(StrictModel):
    site_url: HttpUrl
    role_profile: str
    run_dir: str
    tasks_file: str
    validated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_tasks: int
    pass_count: int = 0
    partial_count: int = 0
    fail_count: int = 0
    results: list[TaskValidationTaskResult] = Field(default_factory=list)


class RuntimeLookupMode(StrEnum):
    PAGE = "page"
    PAGE_TYPE = "page_type"
    PATH = "path"
    TASK_VALIDATION = "task_validation"


class RuntimeConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RuntimeContractIntent(StrictModel):
    """Stable runtime-facing query intent summary."""

    query_intent: str
    task_intent: str
    concept_families: list[str]


class RuntimeContractSource(StrictModel):
    """Runtime-facing provenance for a returned knowledge bundle."""

    name: str | None
    type: str | None
    url: str | None
    canonical_url: str | None
    path: str
    document_title: str
    section_title: str | None
    heading_path: list[str]


class RuntimeContractDiagnostics(StrictModel):
    """Minimal runtime diagnostics for debugging orchestration issues."""

    ranking_explanation: str | None
    support_reason: str | None
    token_count: int
    selection_strategy: str


class SharedRuntimeContractContent(BaseModel):
    """Tool-specific runtime payload carried inside the shared outer envelope.

    The shared cross-tool contract intentionally does not constrain the inner
    shape beyond "must be an object". `agentic_docs` layers its richer content
    model on top of this shared shell.
    """

    model_config = ConfigDict(extra="allow")


class SharedRuntimeContractResult(StrictModel):
    """Shared cross-tool runtime result wrapper.

    This preserves the common provenance and diagnostics shape while allowing
    each tool to define its own `content` payload.
    """

    id: str
    type: str
    rank: int
    confidence: Literal["high", "medium", "low"]
    source: RuntimeContractSource
    content: SharedRuntimeContractContent
    diagnostics: RuntimeContractDiagnostics


class SharedRuntimeContractEnvelope(StrictModel):
    """Canonical shared outer envelope for the Moodle agentic tool family."""

    tool: str
    version: str
    query: str
    normalized_query: str
    intent: RuntimeContractIntent
    results: list[SharedRuntimeContractResult]


RuntimeContractResult = SharedRuntimeContractResult
RuntimeContractEnvelope = SharedRuntimeContractEnvelope
