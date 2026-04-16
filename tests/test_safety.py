# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from moodle_sitemap.models import (
    ActionAffordance,
    AffordanceElementType,
    FormAffordance,
    FormFieldAffordance,
    FormPurpose,
    PageAffordances,
    PageRiskLevel,
    SafetyHints,
)
from moodle_sitemap.safety import summarize_page_safety


def test_summarize_page_safety_marks_low_for_navigation_only_page() -> None:
    summary = summarize_page_safety(
        PageAffordances(
            actions=[
                ActionAffordance(
                    label="Dashboard",
                    url="https://example.com/my",
                    element_type=AffordanceElementType.LINK,
                    safety=SafetyHints(inspect_only=True, navigation_safe=True),
                )
            ]
        )
    )

    assert summary.page_risk_level == PageRiskLevel.LOW
    assert summary.contains_mutating_actions is False
    assert summary.navigation_safe_action_count == 1


def test_summarize_page_safety_marks_medium_for_mutating_form() -> None:
    summary = summarize_page_safety(
        PageAffordances(
            forms=[
                FormAffordance(
                    method="post",
                    action="https://example.com/course/edit.php",
                    fields=[FormFieldAffordance(name="fullname")],
                    purpose=FormPurpose.EDIT_FORM,
                    safety=SafetyHints(likely_mutating=True),
                )
            ]
        )
    )

    assert summary.page_risk_level == PageRiskLevel.MEDIUM
    assert summary.contains_mutating_actions is True


def test_summarize_page_safety_marks_high_for_destructive_or_sesskey_backed_actions() -> None:
    summary = summarize_page_safety(
        PageAffordances(
            actions=[
                ActionAffordance(
                    label="Delete course",
                    url="https://example.com/course/delete.php?id=4&sesskey=abc",
                    element_type=AffordanceElementType.LINK,
                    safety=SafetyHints(likely_mutating=True, likely_destructive=True),
                )
            ]
        )
    )

    assert summary.page_risk_level == PageRiskLevel.HIGH
    assert summary.contains_destructive_actions is True
    assert summary.contains_sesskey_backed_actions is True
