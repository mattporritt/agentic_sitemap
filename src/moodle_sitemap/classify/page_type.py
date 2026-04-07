from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from moodle_sitemap.models import PageFeatures, PageType


def classify_page(url: str, features: PageFeatures) -> PageType:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    classes = {cls.lower() for cls in features.body_classes}
    breadcrumbs = " / ".join(item.lower() for item in features.breadcrumbs)
    body_id = (features.body_id or "").lower()

    if path == "/calendar/view.php" or body_id == "page-calendar-view" or "calendar" in breadcrumbs:
        return PageType.CALENDAR

    if path == "/user/files.php" or body_id == "page-user-files":
        return PageType.PRIVATE_FILES

    if path == "/message/index.php" or body_id == "page-message-index":
        return PageType.MESSAGES

    if path == "/message/notificationpreferences.php" or body_id == "page-message-notificationpreferences":
        return PageType.MESSAGE_PREFERENCES

    if path == "/message/output/popup/notifications.php" or body_id == "page-message-output-popup-notifications":
        return PageType.NOTIFICATIONS

    if _is_dashboard_page(path=path, body_id=body_id, classes=classes):
        return PageType.DASHBOARD

    if path == "/user/preferences.php" or body_id == "page-user-preferences":
        return PageType.USER_PREFERENCES

    if path == "/reportbuilder/index.php" or "report builder" in breadcrumbs or "reportbuilder" in body_id:
        return PageType.REPORT_BUILDER

    if path == "/course/edit.php" and ("id" in query or "course" in breadcrumbs or "page-course-edit" in classes):
        return PageType.COURSE_EDIT

    if path == "/course/view.php" or "course-view" in classes or "course" in breadcrumbs:
        if "id" in query or "page-course-view" in classes:
            return PageType.COURSE_VIEW

    if path == "/course/modedit.php" or body_id == "page-course-modedit":
        return PageType.ACTIVITY_EDIT

    if path.startswith("/mod/") and path.endswith("/view.php"):
        return PageType.ACTIVITY_VIEW
    if "activity" in breadcrumbs and path.endswith("/view.php"):
        return PageType.ACTIVITY_VIEW

    if path.startswith("/admin/") or "admin" in breadcrumbs or "path-admin" in classes:
        return PageType.ADMIN_SETTINGS

    if path == "/user/profile.php" or "user-profile" in classes:
        return PageType.USER_PROFILE

    if path.startswith("/grade/") or "grade" in breadcrumbs or "gradebook" in classes:
        return PageType.GRADEBOOK

    return PageType.UNKNOWN


def _is_dashboard_page(*, path: str, body_id: str, classes: set[str]) -> bool:
    if path in {"/my", "/my/"}:
        return True
    if body_id == "page-my-index":
        return True
    if "path-my" in classes and "pagelayout-mydashboard" in classes and not path.startswith("/message/"):
        return True
    return False
