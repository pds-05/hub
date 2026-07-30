from __future__ import annotations

import re


STREAM_SELECTOR_PATTERN = re.compile(r"\{(?P<labels>[^{}]*)\}")
USER_LABEL_PATTERN = re.compile(r'(?:^|,)\s*platform_user_id\s*(?P<op>=|!=|=~|!~)\s*"(?P<value>[^"]*)"')


def scope_logql(expression: str, user_id: int) -> str:
    user_matcher = f'platform_user_id="{user_id}"'

    def add_scope(match: re.Match[str]) -> str:
        labels = match.group("labels").strip()
        existing = USER_LABEL_PATTERN.search(labels)
        if existing:
            if existing.group("op") == "=" and existing.group("value") == str(user_id):
                return match.group(0)
            raise ValueError("LogQL 不允许查询其他用户的 platform_user_id")
        scoped = f"{labels},{user_matcher}" if labels else user_matcher
        return f"{{{scoped}}}"

    scoped, count = STREAM_SELECTOR_PATTERN.subn(add_scope, expression)
    if not count:
        raise ValueError("LogQL 必须包含日志流选择器")
    return scoped