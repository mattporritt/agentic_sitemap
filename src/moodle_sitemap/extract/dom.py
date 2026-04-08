from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from moodle_sitemap.models import EditorSummary, FormSummary, LabelledElement, PageFeatures


def extract_anchor_hrefs(page: Page) -> list[str]:
    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll("a[href]"))
          .map((anchor) => anchor.href || anchor.getAttribute("href"))
          .filter(Boolean)
        """
    )


def extract_page_features(page: Page) -> PageFeatures:
    payload = page.evaluate(
        """
        () => {
          const cleanText = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const visibleText = (element) => {
            const style = window.getComputedStyle(element);
            if (style.display === "none" || style.visibility === "hidden") {
              return "";
            }
            return cleanText(element.innerText || element.textContent || "");
          };

          const body = document.body || document.querySelector("body");
          const forms = Array.from(document.querySelectorAll("form")).map((form) => ({
            id: cleanText(form.getAttribute("id")) || null,
            method: cleanText(form.getAttribute("method")) || null,
            action: cleanText(form.getAttribute("action")) || null,
            field_names: Array.from(form.querySelectorAll("input, select, textarea"))
              .map((field) => field.getAttribute("name"))
              .filter(Boolean),
          }));

          const links = Array.from(document.querySelectorAll("a[href]"))
            .map((anchor) => ({
              label: visibleText(anchor),
              url: anchor.href || anchor.getAttribute("href"),
            }))
            .filter((item) => item.label);

          const buttons = Array.from(document.querySelectorAll("button, input[type='button'], input[type='submit']"))
            .map((button) => ({
              label: visibleText(button) || cleanText(button.getAttribute("value")),
              url: null,
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
            body_id: body ? body.id || null : null,
            body_classes: body ? Array.from(body.classList) : [],
            breadcrumbs,
            forms,
            editors: {
              has_tinymce: Boolean(document.querySelector(".tox, .tox-tinymce")),
              has_atto: Boolean(document.querySelector(".editor_atto, [data-editor='atto']")),
              has_textarea: Boolean(document.querySelector("textarea")),
            },
            links,
            buttons,
          };
        }
        """
    )

    return build_page_features_from_payload(payload)


def build_page_features_from_payload(payload: dict) -> PageFeatures:
    return PageFeatures(
        body_id=(payload.get("body_id") or None),
        body_classes=normalize_body_classes(payload.get("body_classes", [])),
        breadcrumbs=normalize_breadcrumbs(payload.get("breadcrumbs", [])),
        forms=normalize_forms(payload.get("forms", [])),
        editors=EditorSummary(**payload.get("editors", {})),
        links=[LabelledElement(**item) for item in payload.get("links", [])],
        buttons=[LabelledElement(**item) for item in payload.get("buttons", [])],
    )


def normalize_forms(values: list[dict] | None) -> list[FormSummary]:
    normalized: list[FormSummary] = []
    for value in values or []:
        if not isinstance(value, dict):
            continue
        normalized.append(
            FormSummary(
                id=normalize_scalar_text(value.get("id")),
                method=normalize_scalar_text(value.get("method")),
                action=normalize_scalar_text(value.get("action")),
                field_names=normalize_string_list(value.get("field_names", [])),
            )
        )
    return normalized


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
