from moodle_sitemap.extract.dom import (
    build_page_features_from_payload,
    derive_page_task_summary,
    infer_form_purpose,
    normalize_body_classes,
    normalize_breadcrumbs,
    normalize_actions,
    normalize_filter_controls,
    normalize_forms,
)
from moodle_sitemap.models import FormFieldAffordance, FormPurpose, ImportanceLevel, LikelyIntent, MutationStrength, PageAffordances


def test_normalize_body_classes_deduplicates_and_preserves_order() -> None:
    result = normalize_body_classes([" path-my ", "theme", "path-my", "", "theme"])
    assert result == ["path-my", "theme"]


def test_normalize_breadcrumbs_deduplicates_and_ignores_empty_values() -> None:
    result = normalize_breadcrumbs(["Home", "Dashboard", "Dashboard", "", " "])
    assert result == ["Home", "Dashboard"]


def test_build_page_features_from_payload_normalizes_body_and_breadcrumbs() -> None:
    payload = {
        "body_id": "page-my-index",
        "body_classes": [" path-my ", "theme", "path-my"],
        "breadcrumbs": ["Home", "Dashboard", "Home"],
        "affordances": {
            "actions": [],
            "navigation": [],
            "forms": [],
            "editors": {},
            "file_inputs": [],
            "filters": [],
            "tabs": [],
            "tables": [],
            "lists": [],
            "sections": [],
        },
    }

    features = build_page_features_from_payload(payload)

    assert features.body_id == "page-my-index"
    assert features.body_classes == ["path-my", "theme"]
    assert features.breadcrumbs == ["Home", "Dashboard"]


def test_normalize_forms_drops_object_like_scalar_values() -> None:
    forms = normalize_forms(
        [
            {
                "id": {"0": "ref: <Node>", "1": "ref: <Node>"},
                "method": " post ",
                "action": None,
                "fields": [
                    {"name": " sesskey ", "field_type": "hidden"},
                    {"name": {"bad": "value"}, "field_type": "text"},
                    {"name": "name", "field_type": "text"},
                ],
            }
        ]
    )

    assert len(forms) == 1
    assert forms[0].id is None
    assert forms[0].method == "post"
    assert forms[0].action is None
    assert [field.name for field in forms[0].fields] == ["sesskey", None, "name"]


def test_build_page_features_from_payload_tolerates_malformed_form_entries() -> None:
    payload = {
        "body_id": "page-admin-index",
        "body_classes": [],
        "breadcrumbs": [],
        "affordances": {
            "actions": [],
            "navigation": [],
            "forms": [
                {
                    "id": {"0": "ref: <Node>"},
                    "method": "get",
                    "action": "/admin/search.php",
                    "fields": [{"name": "query", "field_type": "text", "visible": True, "required": False}],
                    "submit_controls": [{"label": "Search", "element_type": "submit"}],
                },
                "not-a-form",
            ],
            "editors": {},
            "file_inputs": [],
            "filters": [],
            "tabs": [],
            "tables": [],
            "lists": [],
            "sections": [],
        },
    }

    features = build_page_features_from_payload(payload)

    assert len(features.affordances.forms) == 1
    assert features.affordances.forms[0].id is None
    assert features.affordances.forms[0].method == "get"
    assert features.affordances.forms[0].action == "/admin/search.php"
    assert features.affordances.forms[0].fields[0].name == "query"
    assert features.affordances.forms[0].purpose == FormPurpose.SEARCH_FORM


def test_normalize_actions_adds_safety_hints() -> None:
    actions = normalize_actions(
        [
            {
                "label": "Delete badge",
                "url": "https://example.com/badges/delete.php?id=2",
                "element_type": "button",
                "class_name": "btn btn-danger",
                "disabled": False,
                "confirms": "confirm('Are you sure?')",
            },
            {
                "label": "Course 1",
                "url": "https://example.com/course/view.php?id=2",
                "element_type": "link",
                "class_name": "nav-link",
                "disabled": False,
            },
        ]
    )

    assert actions[0].safety.likely_destructive is True
    assert actions[0].safety.requires_confirmation_likely is True
    assert actions[1].safety.navigation_safe is True
    assert actions[1].safety.inspect_only is True


def test_infer_form_purpose_distinguishes_search_and_edit_forms() -> None:
    search_purpose = infer_form_purpose(
        method="get",
        action="/admin/search.php",
        fields=[FormFieldAffordance(name="query", label="Search", field_type="text")],
        submit_controls=[],
    )
    edit_purpose = infer_form_purpose(
        method="post",
        action="/course/edit.php",
        fields=[FormFieldAffordance(name="fullname", label="Course full name", field_type="text")],
        submit_controls=normalize_actions([{"label": "Save changes", "element_type": "submit"}]),
    )

    assert search_purpose == FormPurpose.SEARCH_FORM
    assert edit_purpose == FormPurpose.EDIT_FORM


def test_build_page_features_from_payload_extracts_richer_affordances() -> None:
    payload = {
        "body_id": "page-admin-search",
        "body_classes": ["path-admin"],
        "breadcrumbs": ["Administration", "Search"],
        "affordances": {
            "actions": [{"label": "Turn editing on", "element_type": "button", "class_name": "btn btn-primary"}],
            "navigation": [{"label": "Site administration", "url": "https://example.com/admin/search.php", "kind": "secondary-navigation", "current": True}],
            "forms": [],
            "editors": {"has_atto": True},
            "file_inputs": [{"name": "attachments", "label": "Upload file", "accept": ".zip", "multiple": True}],
            "filters": [{"name": "query", "label": "Search", "control_type": "text"}],
            "tabs": [{"label": "Users", "url": "https://example.com/admin/category.php?category=users", "current": False}],
            "tables": [{"region_label": "Users", "column_headers": ["Name", "Email"], "row_count": 25}],
            "lists": [{"region_label": "Quick links", "item_count": 5, "list_type": "ul"}],
            "sections": [{"label": "User accounts", "kind": "accordion-button"}],
        },
    }

    features = build_page_features_from_payload(payload)

    assert features.affordances.actions[0].action_key == "turn-editing-on"
    assert features.affordances.actions[0].safety.likely_mutating is True
    assert features.affordances.actions[0].importance_level == ImportanceLevel.PRIMARY
    assert features.affordances.navigation[0].current is True
    assert features.affordances.editors.has_atto is True
    assert features.affordances.file_inputs[0].multiple is True
    assert features.affordances.filters[0].label == "Search"
    assert features.affordances.tabs[0].label == "Users"
    assert features.affordances.tables[0].row_count == 25
    assert features.affordances.lists[0].item_count == 5
    assert features.affordances.sections[0].label == "User accounts"
    assert features.task_summary.primary_actions == ["Turn editing on"]
    assert features.task_summary.primary_page_intent == LikelyIntent.EDIT


def test_normalize_filter_controls_assigns_search_filter_sort_purposes() -> None:
    controls = normalize_filter_controls(
        [
            {"name": "query", "label": "Search", "control_type": "text"},
            {"name": "sort", "label": "Sort by", "control_type": "select"},
            {"name": "statusfilter", "label": "Filter status", "control_type": "select"},
        ]
    )

    assert [control.purpose.value for control in controls] == ["search", "sort", "filter"]


def test_normalize_actions_sets_importance_and_intent() -> None:
    actions = normalize_actions(
        [
            {
                "label": "Save changes",
                "element_type": "submit",
                "class_name": "btn btn-primary",
            },
            {
                "label": "More actions",
                "element_type": "menu_trigger",
                "class_name": "dropdown-toggle",
                "data_action": "toggle-menu",
            },
        ]
    )

    assert actions[0].importance_level == ImportanceLevel.PRIMARY
    assert actions[0].likely_intent == LikelyIntent.SAVE
    assert actions[0].prominence_score >= 90
    assert actions[1].in_menu_or_overflow is True
    assert actions[1].importance_level == ImportanceLevel.SECONDARY


def test_normalize_forms_assigns_intent_importance_and_mutation_strength() -> None:
    forms = normalize_forms(
        [
            {
                "id": "messageform",
                "method": "post",
                "action": "/message/index.php",
                "fields": [{"name": "message", "label": "Message", "field_type": "textarea", "visible": True}],
                "submit_controls": [{"label": "Send message", "element_type": "submit", "class_name": "btn btn-primary"}],
            }
        ]
    )

    assert forms[0].purpose == FormPurpose.MESSAGE_FORM
    assert forms[0].likely_intent == LikelyIntent.MESSAGE
    assert forms[0].importance_level == ImportanceLevel.PRIMARY
    assert forms[0].likely_mutation_strength == MutationStrength.MEDIUM
    assert forms[0].central_to_page is True


def test_derive_page_task_summary_prefers_high_prominence_actions() -> None:
    summary = derive_page_task_summary(
        PageAffordances(
            actions=normalize_actions(
                [
                    {"label": "Save changes", "element_type": "submit", "class_name": "btn btn-primary"},
                    {"label": "Cancel", "element_type": "link"},
                ]
            ),
            forms=[],
        )
    )

    assert summary.primary_page_intent == LikelyIntent.SAVE
    assert summary.primary_actions[0] == "Save changes"
    assert summary.task_relevance_score > 0
