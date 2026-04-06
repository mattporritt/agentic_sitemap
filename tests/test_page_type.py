from moodle_sitemap.classify.page_type import classify_page
from moodle_sitemap.models import EditorSummary, PageFeatures, PageType


def make_features(
    *,
    body_classes: list[str] | None = None,
    breadcrumbs: list[str] | None = None,
) -> PageFeatures:
    return PageFeatures(
        body_classes=body_classes or [],
        breadcrumbs=breadcrumbs or [],
        forms=[],
        editors=EditorSummary(),
        links=[],
        buttons=[],
    )


def test_classify_dashboard() -> None:
    page_type = classify_page(
        "https://example.com/my/",
        make_features(body_classes=["pagelayout-mydashboard"]),
    )
    assert page_type == PageType.DASHBOARD


def test_classify_course_view() -> None:
    page_type = classify_page(
        "https://example.com/course/view.php?id=7",
        make_features(body_classes=["page-course-view"]),
    )
    assert page_type == PageType.COURSE_VIEW


def test_classify_activity_view() -> None:
    page_type = classify_page(
        "https://example.com/mod/forum/view.php?id=14",
        make_features(),
    )
    assert page_type == PageType.ACTIVITY_VIEW


def test_classify_admin_settings() -> None:
    page_type = classify_page(
        "https://example.com/admin/settings.php?section=users",
        make_features(),
    )
    assert page_type == PageType.ADMIN_SETTINGS


def test_classify_user_profile() -> None:
    page_type = classify_page(
        "https://example.com/user/profile.php?id=3",
        make_features(),
    )
    assert page_type == PageType.USER_PROFILE


def test_classify_gradebook() -> None:
    page_type = classify_page(
        "https://example.com/grade/report/grader/index.php?id=2",
        make_features(),
    )
    assert page_type == PageType.GRADEBOOK
