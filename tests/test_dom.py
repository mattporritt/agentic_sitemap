from moodle_sitemap.extract.dom import (
    build_page_features_from_payload,
    normalize_body_classes,
    normalize_breadcrumbs,
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
