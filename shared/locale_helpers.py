#!/usr/bin/env python3
"""Locale detection utilities for diet mode gating.

Determines whether a user is in China region / Chinese-speaking based on
USER.md Timezone and Language fields, following this priority:

1. If Timezone matches any of the China timezones → China user
2. If Timezone is missing or unrecognized → check Language
   - If Language is zh/zh-CN/zh-HK/zh-TW/zh-MO → China user
   - Otherwise → non-China user

Hong Kong, Macau, Taiwan count as China users.
Singapore, Malaysia do NOT count as China users.
"""

import re
from pathlib import Path


# China timezones (includes mainland + HK/Macau/Taiwan)
CHINA_TIMEZONES = {
    'Asia/Shanghai',
    'Asia/Hong_Kong',
    'Asia/Taipei',
    'Asia/Urumqi',
    'Asia/Macau',
}

# Chinese language codes
CHINESE_LANGUAGES = {
    'zh',
    'zh-CN',
    'zh-HK',
    'zh-TW',
    'zh-MO',
}


def is_china_user(workspace_path: Path) -> bool:
    """
    Determine if user is China region / Chinese-speaking.

    Args:
        workspace_path: Path to user workspace directory

    Returns:
        True if China user, False otherwise (including when USER.md missing)
    """
    user_md = workspace_path / 'USER.md'
    if not user_md.exists():
        return False

    content = user_md.read_text(encoding='utf-8')

    # Step 1: Check Timezone
    tz_match = re.search(r'\*\*Timezone:\*\*\s*([A-Za-z_/]+)', content)
    if tz_match:
        tz = tz_match.group(1).strip()
        if tz in CHINA_TIMEZONES:
            return True

    # Step 2: Timezone missing/unrecognized → check Language
    lang_match = re.search(r'\*\*Language:\*\*\s*([a-zA-Z-]+)', content)
    if lang_match:
        lang = lang_match.group(1).strip()
        return lang in CHINESE_LANGUAGES

    return False
