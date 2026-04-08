from __future__ import annotations

from urllib.parse import parse_qsl, urlparse

from moodle_sitemap.models import ActionAffordance, PageAffordances, PageRiskLevel, PageSafetySummary


def summarize_page_safety(affordances: PageAffordances) -> PageSafetySummary:
    actions = list(affordances.actions)
    actions.extend(control for form in affordances.forms for control in form.submit_controls)

    contains_mutating_actions = any(
        action.safety.likely_mutating for action in actions
    ) or any(form.safety.likely_mutating for form in affordances.forms)
    contains_destructive_actions = any(
        action.safety.likely_destructive for action in actions
    ) or any(form.safety.likely_destructive for form in affordances.forms)
    likely_requires_confirmation = any(
        action.safety.requires_confirmation_likely for action in actions
    ) or any(form.safety.requires_confirmation_likely for form in affordances.forms)
    contains_sesskey_backed_actions = any(has_sesskey_signal(action.url) for action in actions) or any(
        form_contains_sesskey(form) for form in affordances.forms
    )
    navigation_safe_action_count = sum(1 for action in actions if action.safety.navigation_safe)
    mutating_action_count = sum(1 for action in actions if action.safety.likely_mutating)
    mutating_action_count += sum(1 for form in affordances.forms if form.safety.likely_mutating)

    page_risk_level = PageRiskLevel.LOW
    if contains_destructive_actions or (contains_mutating_actions and contains_sesskey_backed_actions):
        page_risk_level = PageRiskLevel.HIGH
    elif contains_mutating_actions or contains_sesskey_backed_actions or likely_requires_confirmation:
        page_risk_level = PageRiskLevel.MEDIUM

    return PageSafetySummary(
        page_risk_level=page_risk_level,
        contains_mutating_actions=contains_mutating_actions,
        contains_destructive_actions=contains_destructive_actions,
        likely_requires_confirmation=likely_requires_confirmation,
        contains_sesskey_backed_actions=contains_sesskey_backed_actions,
        navigation_safe_action_count=navigation_safe_action_count,
        mutating_action_count=mutating_action_count,
    )


def has_sesskey_signal(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    return "sesskey" in query_keys


def form_contains_sesskey(form) -> bool:
    if has_sesskey_signal(form.action):
        return True
    return any((field.name or "").lower() == "sesskey" for field in form.fields)
