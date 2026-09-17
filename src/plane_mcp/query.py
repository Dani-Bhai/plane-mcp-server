from __future__ import annotations

from collections.abc import Mapping


def escape_pql_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_work_item_pql(
    *,
    state: str | None = None,
    assignee: str | None = None,
    label: str | None = None,
    cycle: str | None = None,
    module: str | None = None,
    milestone: str | None = None,
    priority: str | None = None,
    target_date_before: str | None = None,
    target_date_after: str | None = None,
    pql: str | None = None,
) -> str | None:
    clauses: list[str] = []
    equality_filters: Mapping[str, str | None] = {
        "state": state,
        "assignee": assignee,
        "label": label,
        "cycle": cycle,
        "module": module,
        "milestone": milestone,
        "priority": priority,
    }

    for field, value in equality_filters.items():
        if value:
            clauses.append(f'{field} = "{escape_pql_value(value)}"')

    if target_date_before:
        clauses.append(f'target_date <= "{escape_pql_value(target_date_before)}"')
    if target_date_after:
        clauses.append(f'target_date >= "{escape_pql_value(target_date_after)}"')
    if pql:
        clauses.append(f"({pql})")

    return " AND ".join(clauses) or None
