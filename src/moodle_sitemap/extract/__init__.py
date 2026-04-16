# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from .dom import (
    build_page_features_from_payload,
    extract_anchor_hrefs,
    extract_page_features,
    normalize_body_classes,
    normalize_breadcrumbs,
)
from .footer import extract_footer_info, parse_footer_text

__all__ = [
    "build_page_features_from_payload",
    "extract_anchor_hrefs",
    "extract_page_features",
    "extract_footer_info",
    "normalize_body_classes",
    "normalize_breadcrumbs",
    "parse_footer_text",
]
