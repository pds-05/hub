from __future__ import annotations

import re


SELECTOR_PATTERN = re.compile(r"(?P<metric>[a-zA-Z_:][a-zA-Z0-9_:]*)?\{(?P<labels>[^{}]*)\}")
METRIC_PATTERN = re.compile(r"(?<![a-zA-Z0-9_:])(?P<metric>[a-zA-Z_:][a-zA-Z0-9_:]*)(?![a-zA-Z0-9_:]|\s*\()")
STRING_PATTERN = re.compile(r'"(?:\\.|[^"\\])*"')
GROUPING_PATTERN = re.compile(r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^()]*\)")
USER_LABEL_PATTERN = re.compile(r'(?:^|,)\s*platform_user_id\s*(?P<op>=|!=|=~|!~)\s*"(?P<value>[^"]*)"')
PROMQL_KEYWORDS = {
    "and", "bool", "bottomk", "by", "count", "count_values", "day_of_month", "day_of_week",
    "days_in_month", "group", "group_left", "group_right", "hour", "ignoring", "label_join",
    "label_replace", "max", "min", "minute", "month", "offset", "on", "or", "quantile",
    "scalar", "sort", "sort_desc", "stddev", "stdvar", "sum", "time", "timestamp", "topk",
    "unless", "vector", "without", "year",
}


def scope_promql(expression: str, user_id: int) -> str:
    user_matcher = f'platform_user_id="{user_id}"'

    def add_scope(match: re.Match[str]) -> str:
        labels = match.group("labels").strip()
        existing = USER_LABEL_PATTERN.search(labels)
        if existing:
            if existing.group("op") == "=" and existing.group("value") == str(user_id):
                return match.group(0)
            raise ValueError("PromQL 不允许查询其他用户的 platform_user_id")
        metric = match.group("metric") or ""
        scoped = f"{labels},{user_matcher}" if labels else user_matcher
        return f"{metric}{{{scoped}}}"

    protected: list[str] = []

    def protect(value: str) -> str:
        protected.append(value)
        return f"@@{len(protected) - 1}@@"

    scoped, selector_count = SELECTOR_PATTERN.subn(lambda match: protect(add_scope(match)), expression)
    scoped = STRING_PATTERN.sub(lambda match: protect(match.group(0)), scoped)
    scoped = GROUPING_PATTERN.sub(lambda match: protect(match.group(0)), scoped)

    def add_empty_selector(match: re.Match[str]) -> str:
        metric = match.group("metric")
        if metric in PROMQL_KEYWORDS:
            return metric
        return f'{metric}{{{user_matcher}}}'

    scoped, metric_count = METRIC_PATTERN.subn(add_empty_selector, scoped)
    if not selector_count and not metric_count:
        raise ValueError("无法为该 PromQL 自动添加用户隔离标签")
    for index, value in enumerate(protected):
        scoped = scoped.replace(f"@@{index}@@", value)
    return scoped
