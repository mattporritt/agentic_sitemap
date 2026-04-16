# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

"""Deterministic Moodle page classification rules.

The taxonomy is intentionally small and route-driven. When in doubt, prefer a
conservative existing type or `unknown` over creating a clever but ambiguous
rule.
"""

from urllib.parse import parse_qs, urlparse

from moodle_sitemap.models import PageFeatures, PageType


def classify_page(url: str, features: PageFeatures) -> PageType:
    """Classify one rendered page using stable Moodle-aware cues."""

    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    classes = {cls.lower() for cls in features.body_classes}
    breadcrumbs = " / ".join(item.lower() for item in features.breadcrumbs)
    body_id = (features.body_id or "").lower()

    if path == "/calendar/view.php" or body_id == "page-calendar-view" or "calendar" in breadcrumbs:
        return PageType.CALENDAR

    if path == "/course/switchrole.php" or body_id == "page-course-switchrole":
        return PageType.COURSE_SWITCH_ROLE

    if path == "/user/files.php" or body_id == "page-user-files":
        return PageType.PRIVATE_FILES

    if path == "/user/edit.php" or body_id == "page-user-edit":
        return PageType.USER_PROFILE_EDIT

    if path == "/user/view.php" or body_id == "page-user-view":
        return PageType.USER_PROFILE

    if path == "/message/index.php" or body_id == "page-message-index":
        return PageType.MESSAGES

    if path == "/message/edit.php" or body_id == "page-message-edit":
        return PageType.MESSAGE_PREFERENCES

    if path == "/message/notificationpreferences.php" or body_id == "page-message-notificationpreferences":
        return PageType.MESSAGE_PREFERENCES

    if path == "/message/output/popup/notifications.php" or body_id == "page-message-output-popup-notifications":
        return PageType.NOTIFICATIONS

    if _is_dashboard_page(path=path, body_id=body_id, classes=classes):
        return PageType.DASHBOARD

    if path == "/user/contactsitesupport.php" or body_id == "page-user-contactsitesupport":
        return PageType.CONTACT_SITE_SUPPORT

    if path == "/user/preferences.php" or body_id == "page-user-preferences":
        return PageType.USER_PREFERENCES

    if path in {
        "/login/change_password.php",
        "/report/usersessions/user.php",
        "/user/language.php",
        "/user/forum.php",
        "/user/editor.php",
    }:
        return PageType.USER_SETTINGS_PAGE

    if path == "/user/contentbank.php" or body_id == "page-user-contentbank":
        return PageType.CONTENT_BANK_PREFERENCES

    if path in {
        "/blog/index.php",
        "/blog/preferences.php",
        "/blog/external_blogs.php",
        "/blog/external_blog_edit.php",
    } or body_id.startswith("page-blog-"):
        return PageType.BLOG_PAGE

    if path == "/mod/forum/user.php" or body_id == "page-mod-forum-user":
        return PageType.FORUM_USER_PAGE

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

    if path == "/admin/search.php" or body_id == "page-admin-search":
        return PageType.ADMIN_SEARCH

    if path == "/admin/category.php" or body_id == "page-admin-category":
        return PageType.ADMIN_CATEGORY

    if path == "/admin/settings.php" or body_id == "page-admin-setting":
        return PageType.ADMIN_SETTING_PAGE

    if path.startswith("/admin/tool/") or "tool" in breadcrumbs and path.startswith("/admin/"):
        return PageType.ADMIN_TOOL_PAGE

    if path.startswith("/admin/") or "admin" in breadcrumbs or "path-admin" in classes:
        if "search" in path or "search" in body_id:
            return PageType.ADMIN_SEARCH
        if "category.php" in path:
            return PageType.ADMIN_CATEGORY
        if "settings.php" in path:
            return PageType.ADMIN_SETTING_PAGE
        if "/tool/" in path:
            return PageType.ADMIN_TOOL_PAGE
        return PageType.ADMIN_SETTING_PAGE

    if path == "/user/profile.php" or "user-profile" in classes:
        return PageType.USER_PROFILE

    if path.startswith("/grade/") or "grade" in breadcrumbs or "gradebook" in classes:
        return PageType.GRADEBOOK

    return PageType.UNKNOWN


def _is_dashboard_page(*, path: str, body_id: str, classes: set[str]) -> bool:
    """Detect real dashboard pages without over-trusting layout classes."""

    if path in {"/my", "/my/"}:
        return True
    if body_id == "page-my-index":
        return True
    if "path-my" in classes and "pagelayout-mydashboard" in classes and not path.startswith("/message/"):
        return True
    return False
