# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from moodle_sitemap.classify.page_type import classify_page
from moodle_sitemap.models import PageFeatures, PageType


def make_features(
    *,
    body_id: str | None = None,
    body_classes: list[str] | None = None,
    breadcrumbs: list[str] | None = None,
) -> PageFeatures:
    return PageFeatures(
        body_id=body_id,
        body_classes=body_classes or [],
        breadcrumbs=breadcrumbs or [],
    )


def test_classify_dashboard() -> None:
    page_type = classify_page(
        "https://example.com/my/",
        make_features(body_id="page-my-index", body_classes=["pagelayout-mydashboard", "path-my"]),
    )
    assert page_type == PageType.DASHBOARD


def test_message_index_does_not_false_positive_as_dashboard() -> None:
    page_type = classify_page(
        "https://example.com/message/index.php",
        make_features(
            body_id="page-message-index",
            body_classes=["pagelayout-mydashboard", "path-message", "path-user"],
        ),
    )
    assert page_type == PageType.MESSAGES


def test_specific_body_id_and_path_outrank_dashboard_layout_signal() -> None:
    page_type = classify_page(
        "https://example.com/message/notificationpreferences.php",
        make_features(
            body_id="page-message-notificationpreferences",
            body_classes=["pagelayout-mydashboard", "path-message"],
        ),
    )
    assert page_type == PageType.MESSAGE_PREFERENCES


def test_classify_messages_landing_page() -> None:
    page_type = classify_page(
        "https://example.com/message/index.php",
        make_features(
            body_id="page-message-index",
            body_classes=["pagelayout-mydashboard", "path-message"],
        ),
    )
    assert page_type == PageType.MESSAGES


def test_other_message_routes_do_not_collapse_into_messages() -> None:
    page_type = classify_page(
        "https://example.com/message/notificationpreferences.php",
        make_features(
            body_id="page-message-notificationpreferences",
            body_classes=["path-message"],
        ),
    )
    assert page_type == PageType.MESSAGE_PREFERENCES


def test_classify_course_view() -> None:
    page_type = classify_page(
        "https://example.com/course/view.php?id=7",
        make_features(body_classes=["page-course-view"]),
    )
    assert page_type == PageType.COURSE_VIEW


def test_classify_course_switch_role() -> None:
    page_type = classify_page(
        "https://example.com/course/switchrole.php?id=1&switchrole=-1&returnurl=%2Fmy%2Findex.php",
        make_features(body_classes=["path-course"], body_id="page-course-switchrole"),
    )
    assert page_type == PageType.COURSE_SWITCH_ROLE


def test_classify_activity_view() -> None:
    page_type = classify_page(
        "https://example.com/mod/forum/view.php?id=14",
        make_features(),
    )
    assert page_type == PageType.ACTIVITY_VIEW


def test_classify_activity_edit() -> None:
    page_type = classify_page(
        "https://example.com/course/modedit.php?update=14&return=1",
        make_features(body_classes=["page-course-modedit"]),
    )
    assert page_type == PageType.ACTIVITY_EDIT


def test_classify_admin_search() -> None:
    page_type = classify_page(
        "https://example.com/admin/search.php?query=users",
        make_features(),
    )
    assert page_type == PageType.ADMIN_SEARCH


def test_classify_admin_category() -> None:
    page_type = classify_page(
        "https://example.com/admin/category.php?category=ai",
        make_features(),
    )
    assert page_type == PageType.ADMIN_CATEGORY


def test_classify_admin_setting_page() -> None:
    page_type = classify_page(
        "https://example.com/admin/settings.php?section=users",
        make_features(),
    )
    assert page_type == PageType.ADMIN_SETTING_PAGE


def test_classify_admin_tool_page() -> None:
    page_type = classify_page(
        "https://example.com/admin/tool/admin_presets/index.php",
        make_features(),
    )
    assert page_type == PageType.ADMIN_TOOL_PAGE


def test_classify_user_profile() -> None:
    page_type = classify_page(
        "https://example.com/user/profile.php?id=3",
        make_features(),
    )
    assert page_type == PageType.USER_PROFILE


def test_classify_user_profile_edit() -> None:
    page_type = classify_page(
        "https://example.com/user/edit.php?id=103&returnto=profile",
        make_features(body_id="page-user-edit", body_classes=["path-user"]),
    )
    assert page_type == PageType.USER_PROFILE_EDIT


def test_classify_user_view_as_user_profile() -> None:
    page_type = classify_page(
        "https://example.com/user/view.php?course=4&id=103",
        make_features(body_id="page-user-view", body_classes=["path-user"]),
    )
    assert page_type == PageType.USER_PROFILE


def test_classify_contact_site_support() -> None:
    page_type = classify_page(
        "https://example.com/user/contactsitesupport.php",
        make_features(body_classes=["path-user"], body_id="page-user-contactsitesupport"),
    )
    assert page_type == PageType.CONTACT_SITE_SUPPORT


def test_classify_user_preferences() -> None:
    page_type = classify_page(
        "https://example.com/user/preferences.php",
        make_features(body_classes=["path-user"]),
    )
    assert page_type == PageType.USER_PREFERENCES


def test_classify_user_settings_page() -> None:
    page_type = classify_page(
        "https://example.com/login/change_password.php?id=1",
        make_features(body_classes=["path-login"]),
    )
    assert page_type == PageType.USER_SETTINGS_PAGE


def test_classify_content_bank_preferences() -> None:
    page_type = classify_page(
        "https://example.com/user/contentbank.php?id=103",
        make_features(body_id="page-user-contentbank", body_classes=["path-user"]),
    )
    assert page_type == PageType.CONTENT_BANK_PREFERENCES


def test_classify_private_files() -> None:
    page_type = classify_page(
        "https://example.com/user/files.php",
        make_features(body_classes=["path-user"]),
    )
    assert page_type == PageType.PRIVATE_FILES


def test_classify_message_preferences() -> None:
    page_type = classify_page(
        "https://example.com/message/notificationpreferences.php",
        make_features(body_classes=["path-message"]),
    )
    assert page_type == PageType.MESSAGE_PREFERENCES


def test_classify_message_edit_as_message_preferences() -> None:
    page_type = classify_page(
        "https://example.com/message/edit.php?id=103",
        make_features(body_id="page-message-edit", body_classes=["path-message"]),
    )
    assert page_type == PageType.MESSAGE_PREFERENCES


def test_classify_notifications() -> None:
    page_type = classify_page(
        "https://example.com/message/output/popup/notifications.php",
        make_features(body_classes=["path-message"]),
    )
    assert page_type == PageType.NOTIFICATIONS


def test_classify_calendar() -> None:
    page_type = classify_page(
        "https://example.com/calendar/view.php?view=month",
        make_features(body_classes=["path-calendar"]),
    )
    assert page_type == PageType.CALENDAR


def test_classify_blog_page() -> None:
    page_type = classify_page(
        "https://example.com/blog/preferences.php",
        make_features(body_id="page-blog-preferences"),
    )
    assert page_type == PageType.BLOG_PAGE


def test_classify_forum_user_page() -> None:
    page_type = classify_page(
        "https://example.com/mod/forum/user.php?id=103&mode=discussions",
        make_features(body_id="page-mod-forum-user"),
    )
    assert page_type == PageType.FORUM_USER_PAGE


def test_classify_report_builder() -> None:
    page_type = classify_page(
        "https://example.com/reportbuilder/index.php",
        make_features(breadcrumbs=["Report builder", "Custom reports"]),
    )
    assert page_type == PageType.REPORT_BUILDER


def test_classify_course_edit() -> None:
    page_type = classify_page(
        "https://example.com/course/edit.php?id=7",
        make_features(body_classes=["path-course"]),
    )
    assert page_type == PageType.COURSE_EDIT


def test_classify_gradebook() -> None:
    page_type = classify_page(
        "https://example.com/grade/report/grader/index.php?id=2",
        make_features(),
    )
    assert page_type == PageType.GRADEBOOK


def test_nearby_routes_do_not_overclassify() -> None:
    page_type = classify_page(
        "https://example.com/mod/forum/view.php?id=14",
        make_features(body_id="page-mod-forum-view"),
    )
    assert page_type == PageType.ACTIVITY_VIEW
