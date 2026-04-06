from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from moodle_sitemap.models import EditorSummary, LabelledElement, PageFeatures


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

          const body = document.body;
          const forms = Array.from(document.querySelectorAll("form")).map((form) => ({
            id: form.id || null,
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

          const breadcrumbCandidates = [
            ...document.querySelectorAll(".breadcrumb a, .breadcrumb li, nav[aria-label='breadcrumb'] a, [data-region='breadcrumb'] a")
          ];
          const breadcrumbs = breadcrumbCandidates
            .map((item) => cleanText(item.textContent))
            .filter(Boolean);

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

    return PageFeatures(
        body_id=payload.get("body_id"),
        body_classes=payload.get("body_classes", []),
        breadcrumbs=payload.get("breadcrumbs", []),
        forms=payload.get("forms", []),
        editors=EditorSummary(**payload.get("editors", {})),
        links=[LabelledElement(**item) for item in payload.get("links", [])],
        buttons=[LabelledElement(**item) for item in payload.get("buttons", [])],
    )
