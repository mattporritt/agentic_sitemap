from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from moodle_sitemap.models import PageFeatures, PageType


def classify_page(url: str, features: PageFeatures) -> PageType:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    classes = {cls.lower() for cls in features.body_classes}
    breadcrumbs = " / ".join(item.lower() for item in features.breadcrumbs)

    if path in {"/my", "/my/"} or "pagelayout-mydashboard" in classes:
        return PageType.DASHBOARD

    if path == "/course/view.php" or "course-view" in classes or "course" in breadcrumbs:
        if "id" in query or "page-course-view" in classes:
            return PageType.COURSE_VIEW

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
