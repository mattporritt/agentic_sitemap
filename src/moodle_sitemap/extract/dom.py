# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

"""DOM extraction for page features and affordances.

This module does the heaviest browser-side extraction in the project. It
captures visible controls, form structure, navigation, and lightweight page
purpose hints without interacting with the page.
"""

from collections import Counter
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from moodle_sitemap.models import (
    ActionAffordance,
    AffordanceElementType,
    EditorSummary,
    FileInputAffordance,
    FilterControlAffordance,
    FilterControlPurpose,
    FormAffordance,
    FormFieldAffordance,
    FormFieldType,
    FormPurpose,
    ImportanceLevel,
    LikelyIntent,
    MutationStrength,
    NavigationItem,
    PageAffordances,
    PageFeatures,
    PageTaskSummary,
    PageType,
    SafetyHints,
    SectionAffordance,
    TabAffordance,
    TableAffordance,
    ListRegionAffordance,
)

MUTATING_KEYWORDS = {
    "add",
    "assign",
    "create",
    "delete",
    "edit",
    "import",
    "move",
    "remove",
    "save",
    "submit",
    "turn editing on",
    "turn editing off",
    "update",
    "upload",
}

INTENT_KEYWORDS: list[tuple[LikelyIntent, set[str]]] = [
    (LikelyIntent.DELETE, {"delete", "remove", "trash", "purge"}),
    (LikelyIntent.CREATE, {"add", "new", "create"}),
    (LikelyIntent.SAVE, {"save", "submit"}),
    (LikelyIntent.EDIT, {"edit", "update", "modify"}),
    (LikelyIntent.SEARCH, {"search", "find", "query"}),
    (LikelyIntent.FILTER, {"filter", "refine"}),
    (LikelyIntent.CONFIGURE, {"setting", "settings", "configure", "preferences", "option"}),
    (LikelyIntent.MESSAGE, {"message", "reply", "notification", "chat"}),
    (LikelyIntent.REPORT, {"report", "gradebook", "grader"}),
    (LikelyIntent.UPLOAD, {"upload", "import", "attach"}),
    (LikelyIntent.DOWNLOAD, {"download", "export"}),
    (LikelyIntent.VIEW, {"view", "overview", "open"}),
]

DESTRUCTIVE_KEYWORDS = {
    "delete",
    "drop",
    "purge",
    "remove",
    "trash",
}

CONFIRMATION_KEYWORDS = {
    "confirm",
    "are you sure",
}

SEARCH_KEYWORDS = {"query", "search", "find"}
FILTER_KEYWORDS = {"filter", "filters"}
SORT_KEYWORDS = {"sort", "order"}


def extract_anchor_hrefs(page: Page) -> list[str]:
    """Return all anchor hrefs from the rendered page."""

    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll("a[href]"))
          .map((anchor) => anchor.href || anchor.getAttribute("href"))
          .filter(Boolean)
        """
    )


def extract_page_features(page: Page) -> PageFeatures:
    """Extract page metadata, affordances, and task-summary hints.

    The browser-side payload intentionally returns plain scalars and small
    JSON-compatible structures. Normalization happens again in Python so that
    malformed or surprising markup cannot leak complex values into the saved
    schema.
    """

    payload = page.evaluate(
        """
        () => {
          const cleanText = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const isVisible = (element) => {
            if (!element) {
              return false;
            }
            const style = window.getComputedStyle(element);
            if (style.display === "none" || style.visibility === "hidden") {
              return false;
            }
            const rect = element.getBoundingClientRect();
            return rect.width > 0 || rect.height > 0;
          };
          const visibleText = (element) => {
            if (!isVisible(element)) {
              return "";
            }
            return cleanText(element.innerText || element.textContent || "");
          };
          const className = (element) =>
            typeof element?.className === "string" ? cleanText(element.className) : "";
          const labelForField = (field) => {
            if (!field) {
              return null;
            }
            if (field.labels && field.labels.length) {
              const joined = Array.from(field.labels)
                .map((label) => cleanText(label.textContent))
                .filter(Boolean)
                .join(" ");
              if (joined) {
                return joined;
              }
            }
            const closestLabel = field.closest("label");
            if (closestLabel) {
              const text = cleanText(closestLabel.textContent);
              if (text) {
                return text;
              }
            }
            return cleanText(
              field.getAttribute("aria-label") ||
              field.getAttribute("placeholder") ||
              field.getAttribute("name")
            ) || null;
          };
          const regionLabel = (element) => {
            if (!element) {
              return null;
            }
            const ariaLabel = cleanText(element.getAttribute("aria-label"));
            if (ariaLabel) {
              return ariaLabel;
            }
            const labelledBy = element.getAttribute("aria-labelledby");
            if (labelledBy) {
              const labelNode = document.getElementById(labelledBy);
              const text = cleanText(labelNode?.textContent);
              if (text) {
                return text;
              }
            }
            const heading = element.querySelector("h1, h2, h3, h4, legend, caption");
            return cleanText(heading?.textContent) || null;
          };
          const normalizeUrl = (value) => {
            if (!value) {
              return null;
            }
            try {
              return new URL(value, window.location.href).toString();
            } catch {
              return cleanText(value) || null;
            }
          };
          const body = document.body || document.querySelector("body");

          const rawActions = Array.from(
            document.querySelectorAll("a[href], button, input[type='button'], input[type='submit']")
          )
            .filter((element) => isVisible(element))
            .map((element) => {
              const tagName = element.tagName.toLowerCase();
              const type = cleanText(element.getAttribute("type")).toLowerCase();
              const href = normalizeUrl(element.getAttribute("href") || element.href);
              const formAction = normalizeUrl(element.getAttribute("formaction"));
              const hasPopup =
                element.getAttribute("aria-haspopup") ||
                element.getAttribute("data-toggle") ||
                element.getAttribute("data-action");
              let elementType = "button";
              if (tagName === "a" && hasPopup) {
                elementType = "menu_trigger";
              } else if (tagName === "a") {
                elementType = "link";
              } else if (type === "submit") {
                elementType = "submit";
              }
              return {
                label: visibleText(element) || cleanText(element.getAttribute("value")),
                url: href || formAction,
                element_type: elementType,
                disabled: Boolean(element.disabled) || element.getAttribute("aria-disabled") === "true",
                class_name: className(element),
                aria_label: cleanText(element.getAttribute("aria-label")) || null,
                has_popup: Boolean(hasPopup),
                data_action: cleanText(element.getAttribute("data-action")) || null,
                confirms:
                  element.getAttribute("data-confirmation") ||
                  element.getAttribute("data-confirmation-title") ||
                  element.getAttribute("onclick"),
              };
            })
            .filter((item) => item.label);

          const forms = Array.from(document.querySelectorAll("form")).map((form) => {
            const fields = Array.from(form.querySelectorAll("input, select, textarea")).map((field) => ({
              name: cleanText(field.getAttribute("name")) || null,
              label: labelForField(field),
              field_type:
                field.tagName.toLowerCase() === "textarea"
                  ? "textarea"
                  : field.tagName.toLowerCase() === "select"
                    ? "select"
                    : cleanText(field.getAttribute("type")).toLowerCase() || "text",
              visible: isVisible(field),
              required: Boolean(field.required) || field.getAttribute("aria-required") === "true",
            }));

            const submitControls = Array.from(
              form.querySelectorAll("button, input[type='submit'], input[type='button']")
            )
              .filter((element) => isVisible(element))
              .map((element) => ({
                label: visibleText(element) || cleanText(element.getAttribute("value")),
                url: normalizeUrl(element.getAttribute("formaction")) ||
                  normalizeUrl(form.getAttribute("action")),
                element_type:
                  cleanText(element.getAttribute("type")).toLowerCase() === "submit" ? "submit" : "button",
                disabled: Boolean(element.disabled) || element.getAttribute("aria-disabled") === "true",
                class_name: className(element),
                confirms:
                  element.getAttribute("data-confirmation") ||
                  element.getAttribute("data-confirmation-title") ||
                  element.getAttribute("onclick"),
              }))
              .filter((item) => item.label);

            return {
              id: cleanText(form.getAttribute("id")) || null,
              method: cleanText(form.getAttribute("method")) || null,
              action: normalizeUrl(form.getAttribute("action")),
              class_name: className(form),
              fields,
              submit_controls: submitControls,
            };
          });

          const navigation = Array.from(
            document.querySelectorAll("nav a[href], .secondary-navigation a[href], .moremenu a[href], .navbar a[href]")
          )
            .filter((element) => isVisible(element))
            .map((element) => ({
              label: visibleText(element),
              url: normalizeUrl(element.getAttribute("href") || element.href),
              current:
                element.getAttribute("aria-current") === "page" ||
                element.classList.contains("active") ||
                element.parentElement?.classList.contains("active"),
              kind: cleanText(element.closest("nav, .secondary-navigation, .moremenu, .navbar")?.className) || null,
            }))
            .filter((item) => item.label && item.url);

          const tabs = Array.from(
            document.querySelectorAll("[role='tab'], .nav-tabs a, .nav-tabs button, .tabtree a, .nav-tabs .nav-link")
          )
            .filter((element) => isVisible(element))
            .map((element) => ({
              label: visibleText(element),
              url: normalizeUrl(element.getAttribute("href") || element.href),
              current:
                element.getAttribute("aria-selected") === "true" ||
                element.getAttribute("aria-current") === "page" ||
                element.classList.contains("active"),
            }))
            .filter((item) => item.label);

          const fileInputs = Array.from(
            document.querySelectorAll("input[type='file'], .filepicker input, [data-filetypesbrowser]")
          ).map((field) => ({
            name: cleanText(field.getAttribute("name")) || null,
            label: labelForField(field),
            accept: cleanText(field.getAttribute("accept")) || null,
            multiple: field.hasAttribute("multiple"),
          }));

          const filters = Array.from(document.querySelectorAll("input, select"))
            .filter((field) => isVisible(field))
            .map((field) => ({
              name: cleanText(field.getAttribute("name")) || null,
              label: labelForField(field),
              control_type:
                field.tagName.toLowerCase() === "select"
                  ? "select"
                  : cleanText(field.getAttribute("type")).toLowerCase() || "text",
              hint: cleanText(
                field.getAttribute("name") ||
                field.getAttribute("placeholder") ||
                labelForField(field)
              ).toLowerCase(),
            }))
            .filter((item) => item.hint.includes("search") || item.hint.includes("query") || item.hint.includes("filter") || item.hint.includes("sort"));

          const tables = Array.from(document.querySelectorAll("table"))
            .filter((table) => isVisible(table))
            .map((table) => ({
              region_label: regionLabel(table),
              column_headers: Array.from(table.querySelectorAll("th"))
                .map((item) => cleanText(item.textContent))
                .filter(Boolean),
              row_count: table.tBodies.length
                ? Array.from(table.tBodies).reduce((count, tbody) => count + tbody.querySelectorAll("tr").length, 0)
                : Math.max(table.querySelectorAll("tr").length - 1, 0),
            }));

          const lists = Array.from(document.querySelectorAll("ul, ol, [role='list'], .list-group"))
            .filter((element) => isVisible(element))
            .map((element) => ({
              region_label: regionLabel(element),
              item_count: element.querySelectorAll(":scope > li, :scope > [role='listitem'], :scope > .list-group-item").length,
              list_type: element.tagName.toLowerCase(),
            }))
            .filter((item) => item.item_count >= 3);

          const sections = Array.from(
            document.querySelectorAll(".accordion-button, [role='region'][aria-label], .drawerheader, section h2, section h3")
          )
            .filter((element) => isVisible(element))
            .map((element) => ({
              label: visibleText(element) || cleanText(element.getAttribute("aria-label")),
              kind: element.className ? cleanText(element.className) : element.tagName.toLowerCase(),
            }))
            .filter((item) => item.label);

          const breadcrumbSelectors = [
            ".breadcrumb li",
            ".breadcrumb a",
            ".breadcrumbs li",
            ".breadcrumbs a",
            "nav[aria-label='breadcrumb'] li",
            "nav[aria-label='breadcrumb'] a",
            "[data-region='breadcrumb'] li",
            "[data-region='breadcrumb'] a",
            ".page-context-header .breadcrumb li",
            ".page-context-header .breadcrumb a",
            ".secondary-navigation .breadcrumb-item",
            ".secondary-navigation .breadcrumb-item a"
          ];
          const breadcrumbs = breadcrumbSelectors.flatMap((selector) =>
            Array.from(document.querySelectorAll(selector)).map((item) => cleanText(item.textContent))
          );

          return {
            title: document.title || null,
            body_id: body ? body.id || null : null,
            body_classes: body ? Array.from(body.classList) : [],
            breadcrumbs,
            affordances: {
              actions: rawActions,
              navigation,
              forms,
              editors: {
                has_tinymce: Boolean(document.querySelector(".tox, .tox-tinymce")),
                has_atto: Boolean(document.querySelector(".editor_atto, [data-editor='atto']")),
                has_textarea: Boolean(document.querySelector("textarea")),
              },
              file_inputs: fileInputs,
              filters,
              tabs,
              tables,
              lists,
              sections,
            },
          };
        }
        """
    )

    return build_page_features_from_payload(payload)


def build_page_features_from_payload(payload: dict) -> PageFeatures:
    body_classes = normalize_body_classes(payload.get("body_classes", []))
    breadcrumbs = normalize_breadcrumbs(payload.get("breadcrumbs", []))
    affordances_payload = payload.get("affordances", {})
    affordances = PageAffordances(
        actions=normalize_actions(affordances_payload.get("actions", [])),
        navigation=normalize_navigation_items(affordances_payload.get("navigation", [])),
        forms=normalize_forms(affordances_payload.get("forms", [])),
        editors=EditorSummary(**affordances_payload.get("editors", {})),
        file_inputs=normalize_file_inputs(affordances_payload.get("file_inputs", [])),
        filters=normalize_filter_controls(affordances_payload.get("filters", [])),
        tabs=normalize_tabs(affordances_payload.get("tabs", [])),
        tables=normalize_tables(affordances_payload.get("tables", [])),
        lists=normalize_lists(affordances_payload.get("lists", [])),
        sections=normalize_sections(affordances_payload.get("sections", [])),
    )
    return PageFeatures(
        body_id=(payload.get("body_id") or None),
        body_classes=body_classes,
        breadcrumbs=breadcrumbs,
        affordances=affordances,
        task_summary=derive_page_task_summary(
            affordances,
            title=normalize_scalar_text(payload.get("title")),
            body_id=normalize_scalar_text(payload.get("body_id")),
            body_classes=body_classes,
            breadcrumbs=breadcrumbs,
        ),
    )


def normalize_actions(values: list[dict] | None) -> list[ActionAffordance]:
    normalized: list[ActionAffordance] = []
    seen: set[tuple[str, str | None, str]] = set()
    for value in values or []:
        if not isinstance(value, dict):
            continue
        label = normalize_scalar_text(value.get("label"))
        if not label:
            continue
        url = normalize_scalar_text(value.get("url"))
        element_type = normalize_element_type(value.get("element_type"))
        key = (label, url, element_type.value)
        if key in seen:
            continue
        seen.add(key)
        disabled = bool(value.get("disabled"))
        text_blob = " ".join(
            item
            for item in [
                label.lower(),
                (url or "").lower(),
                normalize_scalar_text(value.get("aria_label")) or "",
                normalize_scalar_text(value.get("data_action")) or "",
                normalize_scalar_text(value.get("class_name")) or "",
                normalize_scalar_text(value.get("confirms")) or "",
            ]
            if item
        )
        mutating = contains_keyword(text_blob, MUTATING_KEYWORDS)
        destructive = contains_keyword(text_blob, DESTRUCTIVE_KEYWORDS)
        confirmation = contains_keyword(text_blob, CONFIRMATION_KEYWORDS) or "data-confirmation" in text_blob
        navigation_safe = element_type in {AffordanceElementType.LINK, AffordanceElementType.TAB} and not mutating and not destructive
        likely_intent = infer_likely_intent(text_blob, default=LikelyIntent.NAVIGATE if navigation_safe else LikelyIntent.UNKNOWN)
        importance_level = infer_action_importance(
            label=label,
            class_name=normalize_scalar_text(value.get("class_name")),
            element_type=element_type,
            likely_intent=likely_intent,
            has_popup=bool(value.get("has_popup")),
        )
        prominence_score = infer_prominence_score(
            importance_level=importance_level,
            is_primary_class=is_primary_class(value.get("class_name")),
            likely_intent=likely_intent,
            in_menu_or_overflow=is_menu_or_overflow(value.get("class_name"), value.get("data_action")),
        )
        normalized.append(
            ActionAffordance(
                label=label,
                url=url,
                element_type=element_type,
                action_key=make_action_key(label),
                importance_level=importance_level,
                likely_intent=likely_intent,
                prominence_score=prominence_score,
                in_primary_region=is_primary_region(value.get("class_name"), label),
                in_menu_or_overflow=is_menu_or_overflow(value.get("class_name"), value.get("data_action")),
                is_primary=is_primary_class(value.get("class_name")),
                disabled=disabled,
                safety=SafetyHints(
                    inspect_only=navigation_safe and not disabled,
                    navigation_safe=navigation_safe,
                    likely_mutating=mutating and not disabled,
                    likely_destructive=destructive and not disabled,
                    requires_confirmation_likely=confirmation,
                ),
            )
        )
    return normalized


def normalize_navigation_items(values: list[dict] | None) -> list[NavigationItem]:
    normalized: list[NavigationItem] = []
    seen: set[tuple[str, str | None]] = set()
    for value in values or []:
        if not isinstance(value, dict):
            continue
        label = normalize_scalar_text(value.get("label"))
        url = normalize_scalar_text(value.get("url"))
        if not label or not url:
            continue
        key = (label, url)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            NavigationItem(
                label=label,
                url=url,
                kind=normalize_scalar_text(value.get("kind")),
                current=bool(value.get("current")),
                importance_level=ImportanceLevel.PRIMARY if bool(value.get("current")) else ImportanceLevel.SECONDARY,
                likely_intent=LikelyIntent.NAVIGATE,
            )
        )
    return normalized


def normalize_forms(values: list[dict] | None) -> list[FormAffordance]:
    normalized: list[FormAffordance] = []
    for value in values or []:
        if not isinstance(value, dict):
            continue
        fields = normalize_form_fields(value.get("fields", []))
        submit_controls = normalize_actions(value.get("submit_controls", []))
        purpose = infer_form_purpose(
            method=normalize_scalar_text(value.get("method")),
            action=normalize_scalar_text(value.get("action")),
            fields=fields,
            submit_controls=submit_controls,
        )
        mutating = purpose in {FormPurpose.EDIT_FORM, FormPurpose.SETTINGS_FORM, FormPurpose.MESSAGE_FORM, FormPurpose.UPLOAD_FORM} or (
            (normalize_scalar_text(value.get("method")) or "").lower() == "post"
            and purpose not in {FormPurpose.SEARCH_FORM, FormPurpose.FILTER_FORM}
        )
        destructive = any(control.safety.likely_destructive for control in submit_controls)
        confirmation = any(control.safety.requires_confirmation_likely for control in submit_controls)
        navigation_safe = not mutating and (normalize_scalar_text(value.get("method")) or "get").lower() == "get"
        likely_intent = form_purpose_to_intent(purpose)
        mutation_strength = infer_mutation_strength(mutating=mutating, destructive=destructive, submit_controls=submit_controls, fields=fields)
        importance_level = infer_form_importance(purpose=purpose, fields=fields, submit_controls=submit_controls)
        normalized.append(
            FormAffordance(
                id=normalize_scalar_text(value.get("id")),
                method=normalize_scalar_text(value.get("method")),
                action=normalize_scalar_text(value.get("action")),
                fields=fields,
                submit_controls=submit_controls,
                purpose=purpose,
                importance_level=importance_level,
                likely_intent=likely_intent,
                likely_mutation_strength=mutation_strength,
                central_to_page=is_form_central_to_page(purpose=purpose, fields=fields),
                safety=SafetyHints(
                    inspect_only=navigation_safe,
                    navigation_safe=navigation_safe,
                    likely_mutating=mutating,
                    likely_destructive=destructive,
                    requires_confirmation_likely=confirmation,
                ),
            )
        )
    return normalized


def normalize_form_fields(values: list[dict] | None) -> list[FormFieldAffordance]:
    normalized: list[FormFieldAffordance] = []
    seen: set[tuple[str | None, str | None, str]] = set()
    for value in values or []:
        if not isinstance(value, dict):
            continue
        field_type = normalize_field_type(value.get("field_type"))
        name = normalize_scalar_text(value.get("name"))
        label = normalize_scalar_text(value.get("label"))
        key = (name, label, field_type.value)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            FormFieldAffordance(
                name=name,
                label=label,
                field_type=field_type,
                visible=bool(value.get("visible", True)),
                required=bool(value.get("required")),
            )
        )
    return normalized


def normalize_file_inputs(values: list[dict] | None) -> list[FileInputAffordance]:
    normalized: list[FileInputAffordance] = []
    seen: set[tuple[str | None, str | None]] = set()
    for value in values or []:
        if not isinstance(value, dict):
            continue
        name = normalize_scalar_text(value.get("name"))
        label = normalize_scalar_text(value.get("label"))
        key = (name, label)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            FileInputAffordance(
                name=name,
                label=label,
                accept=normalize_scalar_text(value.get("accept")),
                multiple=bool(value.get("multiple")),
            )
        )
    return normalized


def normalize_filter_controls(values: list[dict] | None) -> list[FilterControlAffordance]:
    normalized: list[FilterControlAffordance] = []
    seen: set[tuple[str | None, str | None, str]] = set()
    for value in values or []:
        if not isinstance(value, dict):
            continue
        name = normalize_scalar_text(value.get("name"))
        label = normalize_scalar_text(value.get("label"))
        control_type = normalize_field_type(value.get("control_type"))
        purpose = infer_filter_purpose(" ".join(item for item in [name or "", label or ""] if item))
        key = (name, label, purpose.value)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            FilterControlAffordance(
                name=name,
                label=label,
                control_type=control_type,
                purpose=purpose,
            )
        )
    return normalized


def normalize_tabs(values: list[dict] | None) -> list[TabAffordance]:
    normalized: list[TabAffordance] = []
    seen: set[tuple[str, str | None]] = set()
    for value in values or []:
        if not isinstance(value, dict):
            continue
        label = normalize_scalar_text(value.get("label"))
        if not label:
            continue
        url = normalize_scalar_text(value.get("url"))
        key = (label, url)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(TabAffordance(label=label, url=url, current=bool(value.get("current"))))
    return normalized


def normalize_tables(values: list[dict] | None) -> list[TableAffordance]:
    normalized: list[TableAffordance] = []
    for value in values or []:
        if not isinstance(value, dict):
            continue
        row_count = int(value.get("row_count") or 0)
        headers = normalize_string_list(value.get("column_headers", []))
        if row_count <= 0 and not headers:
            continue
        normalized.append(
            TableAffordance(
                region_label=normalize_scalar_text(value.get("region_label")),
                column_headers=headers,
                row_count=row_count,
            )
        )
    return normalized


def normalize_lists(values: list[dict] | None) -> list[ListRegionAffordance]:
    normalized: list[ListRegionAffordance] = []
    for value in values or []:
        if not isinstance(value, dict):
            continue
        item_count = int(value.get("item_count") or 0)
        if item_count <= 0:
            continue
        normalized.append(
            ListRegionAffordance(
                region_label=normalize_scalar_text(value.get("region_label")),
                item_count=item_count,
                list_type=normalize_scalar_text(value.get("list_type")),
            )
        )
    return normalized


def normalize_sections(values: list[dict] | None) -> list[SectionAffordance]:
    normalized: list[SectionAffordance] = []
    seen: set[str] = set()
    for value in values or []:
        if not isinstance(value, dict):
            continue
        label = normalize_scalar_text(value.get("label"))
        if not label or label in seen:
            continue
        seen.add(label)
        normalized.append(
            SectionAffordance(
                label=label,
                kind=normalize_scalar_text(value.get("kind")),
            )
        )
    return normalized


def infer_form_purpose(
    *,
    method: str | None,
    action: str | None,
    fields: list[FormFieldAffordance],
    submit_controls: list[ActionAffordance],
) -> FormPurpose:
    text_blob = " ".join(
        item.lower()
        for item in [
            method or "",
            action or "",
            *[field.name or "" for field in fields],
            *[field.label or "" for field in fields],
            *[control.label for control in submit_controls],
        ]
        if item
    )
    if contains_keyword(text_blob, SEARCH_KEYWORDS):
        return FormPurpose.SEARCH_FORM
    if contains_keyword(text_blob, FILTER_KEYWORDS | SORT_KEYWORDS):
        return FormPurpose.FILTER_FORM
    if "message" in text_blob or "notification" in text_blob:
        return FormPurpose.MESSAGE_FORM
    if contains_keyword(text_blob, {"upload", "import", "file", "attachment"}):
        return FormPurpose.UPLOAD_FORM
    if contains_keyword(text_blob, {"setting", "settings", "preference", "preferences", "option"}):
        return FormPurpose.SETTINGS_FORM
    if contains_keyword(text_blob, MUTATING_KEYWORDS):
        return FormPurpose.EDIT_FORM
    return FormPurpose.UNKNOWN_FORM


def infer_filter_purpose(text: str) -> FilterControlPurpose:
    lowered = text.lower()
    if contains_keyword(lowered, SEARCH_KEYWORDS):
        return FilterControlPurpose.SEARCH
    if contains_keyword(lowered, FILTER_KEYWORDS):
        return FilterControlPurpose.FILTER
    if contains_keyword(lowered, SORT_KEYWORDS):
        return FilterControlPurpose.SORT
    return FilterControlPurpose.UNKNOWN


def contains_keyword(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def infer_likely_intent(text: str, *, default: LikelyIntent = LikelyIntent.UNKNOWN) -> LikelyIntent:
    for intent, keywords in INTENT_KEYWORDS:
        if contains_keyword(text, keywords):
            return intent
    return default


def normalize_element_type(value: object) -> AffordanceElementType:
    if isinstance(value, str):
        lowered = value.strip().lower()
        for item in AffordanceElementType:
            if item.value == lowered:
                return item
    return AffordanceElementType.BUTTON


def normalize_field_type(value: object) -> FormFieldType:
    if isinstance(value, str):
        lowered = value.strip().lower()
        mapping = {
            "search": FormFieldType.TEXT,
            "email": FormFieldType.TEXT,
            "number": FormFieldType.TEXT,
            "password": FormFieldType.TEXT,
            "submit": FormFieldType.OTHER,
        }
        if lowered in mapping:
            return mapping[lowered]
        for item in FormFieldType:
            if item.value == lowered:
                return item
    return FormFieldType.OTHER


def make_action_key(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug or "action"


def is_primary_class(value: object) -> bool:
    text = (normalize_scalar_text(value) or "").lower()
    return any(token in text for token in {"btn-primary", "primary", "singlebutton", "mainbutton"})


def is_primary_region(class_name: object, label: str) -> bool:
    text = (normalize_scalar_text(class_name) or "").lower()
    return is_primary_class(class_name) or any(token in text for token in {"primary", "main", "singlebutton"}) or label.lower().startswith("new ")


def is_menu_or_overflow(class_name: object, data_action: object) -> bool:
    text = " ".join(
        part for part in [(normalize_scalar_text(class_name) or "").lower(), (normalize_scalar_text(data_action) or "").lower()] if part
    )
    return any(token in text for token in {"dropdown", "menu", "overflow", "moremenu"})


def infer_action_importance(
    *,
    label: str,
    class_name: str | None,
    element_type: AffordanceElementType,
    likely_intent: LikelyIntent,
    has_popup: bool,
) -> ImportanceLevel:
    label_lower = label.lower()
    class_text = (class_name or "").lower()
    if is_primary_class(class_name) or label_lower.startswith(("new ", "add ", "create ", "save ", "submit ")) or likely_intent in {
        LikelyIntent.CREATE,
        LikelyIntent.SAVE,
        LikelyIntent.UPLOAD,
    }:
        return ImportanceLevel.PRIMARY
    if element_type in {AffordanceElementType.MENU_TRIGGER} or has_popup or any(token in class_text for token in {"secondary", "nav", "tab"}):
        return ImportanceLevel.SECONDARY
    if likely_intent in {LikelyIntent.NAVIGATE, LikelyIntent.VIEW, LikelyIntent.SEARCH, LikelyIntent.FILTER, LikelyIntent.CONFIGURE, LikelyIntent.MESSAGE}:
        return ImportanceLevel.SECONDARY
    return ImportanceLevel.TERTIARY


def infer_prominence_score(
    *,
    importance_level: ImportanceLevel,
    is_primary_class: bool,
    likely_intent: LikelyIntent,
    in_menu_or_overflow: bool,
) -> int:
    score = {
        ImportanceLevel.PRIMARY: 90,
        ImportanceLevel.SECONDARY: 60,
        ImportanceLevel.TERTIARY: 30,
    }[importance_level]
    if is_primary_class:
        score += 10
    if likely_intent in {LikelyIntent.CREATE, LikelyIntent.SAVE, LikelyIntent.CONFIGURE, LikelyIntent.MESSAGE}:
        score += 5
    if in_menu_or_overflow:
        score -= 15
    return max(0, min(100, score))


def form_purpose_to_intent(purpose: FormPurpose) -> LikelyIntent:
    mapping = {
        FormPurpose.SEARCH_FORM: LikelyIntent.SEARCH,
        FormPurpose.FILTER_FORM: LikelyIntent.FILTER,
        FormPurpose.EDIT_FORM: LikelyIntent.EDIT,
        FormPurpose.SETTINGS_FORM: LikelyIntent.CONFIGURE,
        FormPurpose.MESSAGE_FORM: LikelyIntent.MESSAGE,
        FormPurpose.UPLOAD_FORM: LikelyIntent.UPLOAD,
        FormPurpose.UNKNOWN_FORM: LikelyIntent.UNKNOWN,
    }
    return mapping[purpose]


def infer_mutation_strength(
    *,
    mutating: bool,
    destructive: bool,
    submit_controls: list[ActionAffordance],
    fields: list[FormFieldAffordance],
) -> MutationStrength:
    if destructive:
        return MutationStrength.HIGH
    if not mutating:
        return MutationStrength.NONE
    if any(
        control.likely_intent in {LikelyIntent.SAVE, LikelyIntent.CREATE, LikelyIntent.UPLOAD, LikelyIntent.MESSAGE}
        for control in submit_controls
    ) or len(fields) >= 4:
        return MutationStrength.MEDIUM
    return MutationStrength.LOW


def infer_form_importance(
    *,
    purpose: FormPurpose,
    fields: list[FormFieldAffordance],
    submit_controls: list[ActionAffordance],
) -> ImportanceLevel:
    if purpose in {FormPurpose.EDIT_FORM, FormPurpose.SETTINGS_FORM, FormPurpose.MESSAGE_FORM, FormPurpose.UPLOAD_FORM} and submit_controls:
        return ImportanceLevel.PRIMARY
    if purpose in {FormPurpose.SEARCH_FORM, FormPurpose.FILTER_FORM}:
        return ImportanceLevel.SECONDARY
    if len(fields) >= 5:
        return ImportanceLevel.SECONDARY
    return ImportanceLevel.TERTIARY


def is_form_central_to_page(*, purpose: FormPurpose, fields: list[FormFieldAffordance]) -> bool:
    if purpose in {FormPurpose.MESSAGE_FORM, FormPurpose.UPLOAD_FORM, FormPurpose.SETTINGS_FORM}:
        return True
    if purpose == FormPurpose.EDIT_FORM and len(fields) >= 3:
        return True
    if purpose in {FormPurpose.SEARCH_FORM, FormPurpose.FILTER_FORM} and len(fields) <= 2:
        return False
    return False


def derive_page_task_summary(
    affordances: PageAffordances,
    *,
    title: str | None = None,
    body_id: str | None = None,
    body_classes: list[str] | None = None,
    breadcrumbs: list[str] | None = None,
) -> PageTaskSummary:
    ranked_actions = sorted(
        affordances.actions,
        key=lambda item: (-item.prominence_score, item.importance_level.value, item.label),
    )
    primary_actions = [action.label for action in ranked_actions[:3]]
    intent_counts = Counter()
    for action in affordances.actions:
        if action.likely_intent == LikelyIntent.UNKNOWN:
            continue
        boost = 4 if action.importance_level == ImportanceLevel.PRIMARY else 2 if action.importance_level == ImportanceLevel.SECONDARY else 1
        intent_counts[action.likely_intent] += boost
    for form in affordances.forms:
        if form.likely_intent == LikelyIntent.UNKNOWN:
            continue
        boost = 5 if form.central_to_page else 3 if form.importance_level == ImportanceLevel.PRIMARY else 2
        intent_counts[form.likely_intent] += boost
    for item in affordances.navigation:
        if item.likely_intent == LikelyIntent.UNKNOWN:
            continue
        intent_counts[item.likely_intent] += 2 if item.current else 1
    hint_intent = infer_page_hint_intent(
        title=title,
        body_id=body_id,
        body_classes=body_classes or [],
        breadcrumbs=breadcrumbs or [],
    )
    if hint_intent != LikelyIntent.UNKNOWN:
        intent_counts[hint_intent] += 4
    primary_page_intent = intent_counts.most_common(1)[0][0] if intent_counts else LikelyIntent.UNKNOWN
    task_relevance_score = min(
        100,
        sum(action.prominence_score for action in ranked_actions[:3]) // max(len(ranked_actions[:3]), 1)
        if ranked_actions
        else 0,
    )
    return PageTaskSummary(
        primary_page_intent=primary_page_intent,
        primary_actions=primary_actions,
        task_relevance_score=task_relevance_score,
    )


def infer_page_hint_intent(
    *,
    title: str | None,
    body_id: str | None,
    body_classes: list[str],
    breadcrumbs: list[str],
) -> LikelyIntent:
    hint_text = " ".join(
        part.lower()
        for part in [
            title or "",
            body_id or "",
            " ".join(body_classes),
            " ".join(breadcrumbs),
        ]
        if part
    )
    if any(token in hint_text for token in {"message", "notificationpreferences", "notifications"}):
        return LikelyIntent.MESSAGE
    if any(token in hint_text for token in {"report", "gradebook", "grader"}):
        return LikelyIntent.REPORT
    if any(token in hint_text for token in {"preference", "setting", "admin-setting", "configuration"}):
        return LikelyIntent.CONFIGURE
    if any(token in hint_text for token in {"search", "page-admin-search"}):
        return LikelyIntent.SEARCH
    if any(token in hint_text for token in {"edit", "modedit"}):
        return LikelyIntent.EDIT
    if any(token in hint_text for token in {"upload", "file", "private files"}):
        return LikelyIntent.UPLOAD
    if any(token in hint_text for token in {"course-view", "dashboard", "calendar", "profile"}):
        return LikelyIntent.NAVIGATE
    return LikelyIntent.UNKNOWN


def refine_task_summary_for_page_type(
    page_type: PageType,
    task_summary: PageTaskSummary,
) -> PageTaskSummary:
    intent_overrides = {
        PageType.DASHBOARD: LikelyIntent.NAVIGATE,
        PageType.COURSE_VIEW: LikelyIntent.NAVIGATE,
        PageType.COURSE_EDIT: LikelyIntent.EDIT,
        PageType.ACTIVITY_VIEW: LikelyIntent.VIEW,
        PageType.ACTIVITY_EDIT: LikelyIntent.EDIT,
        PageType.ADMIN_SEARCH: LikelyIntent.SEARCH,
        PageType.ADMIN_CATEGORY: LikelyIntent.CONFIGURE,
        PageType.ADMIN_SETTING_PAGE: LikelyIntent.CONFIGURE,
        PageType.ADMIN_TOOL_PAGE: LikelyIntent.CONFIGURE,
        PageType.USER_PREFERENCES: LikelyIntent.CONFIGURE,
        PageType.MESSAGE_PREFERENCES: LikelyIntent.CONFIGURE,
        PageType.MESSAGES: LikelyIntent.MESSAGE,
        PageType.NOTIFICATIONS: LikelyIntent.MESSAGE,
        PageType.CONTACT_SITE_SUPPORT: LikelyIntent.MESSAGE,
        PageType.PRIVATE_FILES: LikelyIntent.UPLOAD,
        PageType.REPORT_BUILDER: LikelyIntent.REPORT,
        PageType.GRADEBOOK: LikelyIntent.REPORT,
        PageType.CALENDAR: LikelyIntent.VIEW,
    }
    override = intent_overrides.get(page_type)
    if override is None:
        return task_summary
    return PageTaskSummary(
        primary_page_intent=override,
        primary_actions=task_summary.primary_actions,
        task_relevance_score=task_summary.task_relevance_score,
    )


def normalize_scalar_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return cleaned or None
    return None


def normalize_string_list(values: list[object] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        cleaned = normalize_scalar_text(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def normalize_body_classes(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        cleaned = " ".join((value or "").split())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def normalize_breadcrumbs(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        cleaned = " ".join((value or "").split())
        if not cleaned or cleaned in {"#", "/"} or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized
