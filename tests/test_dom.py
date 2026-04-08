from moodle_sitemap.extract.dom import (
    build_page_features_from_payload,
    normalize_body_classes,
    normalize_breadcrumbs,
    normalize_forms,
)


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
        "forms": [],
        "editors": {},
        "links": [],
        "buttons": [],
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
                "field_names": [" sesskey ", {"bad": "value"}, "sesskey", "", "name"],
            }
        ]
    )

    assert len(forms) == 1
    assert forms[0].id is None
    assert forms[0].method == "post"
    assert forms[0].action is None
    assert forms[0].field_names == ["sesskey", "name"]


def test_build_page_features_from_payload_tolerates_malformed_form_entries() -> None:
    payload = {
        "body_id": "page-admin-index",
        "body_classes": [],
        "breadcrumbs": [],
        "forms": [
            {
                "id": {"0": "ref: <Node>"},
                "method": "get",
                "action": "/admin/search.php",
                "field_names": ["query"],
            },
            "not-a-form",
        ],
        "editors": {},
        "links": [],
        "buttons": [],
    }

    features = build_page_features_from_payload(payload)

    assert len(features.forms) == 1
    assert features.forms[0].id is None
    assert features.forms[0].method == "get"
    assert features.forms[0].action == "/admin/search.php"
    assert features.forms[0].field_names == ["query"]
