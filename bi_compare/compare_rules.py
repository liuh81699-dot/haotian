from __future__ import annotations

import copy
import json
from typing import Any


def apply_chart_compare_rules(payload: Any, *, scope: str) -> Any:
    """Apply domain-specific compare rules to reduce false positives.

    Rules:
    - chartMain.data: ignore order, compare full row payload.
    - chartMain.column.values: compare only title fields (ignore order + other attrs).
    - chartMain.row.meta: compare only title fields (ignore order + other attrs).
    - chartMain.row.values: ignore order, compare full row payload.
    """

    cloned = copy.deepcopy(payload)

    if scope == "full_response":
        if isinstance(cloned, dict) and isinstance(cloned.get("chartMain"), dict):
            _apply_to_chart_main(cloned["chartMain"])
        return cloned

    if isinstance(cloned, dict):
        _apply_to_chart_main(cloned)
    return cloned


def _apply_to_chart_main(chart_main: dict[str, Any]) -> None:
    data = chart_main.get("data")
    data_normalized = _sorted_list(data) if isinstance(data, list) else data

    column = chart_main.get("column")
    column_values: Any = None
    if isinstance(column, dict):
        values = column.get("values")
        column_values = _extract_titles(values) if isinstance(values, list) else values

    row = chart_main.get("row")
    row_meta: Any = None
    row_values: Any = None
    if isinstance(row, dict):
        meta = row.get("meta")
        row_meta = _extract_titles(meta) if isinstance(meta, list) else meta
        values = row.get("values")
        row_values = _sorted_list(values) if isinstance(values, list) else values

    # Keep only the requested compare scope to avoid unrelated metadata diffs.
    chart_main.clear()
    chart_main["data"] = data_normalized
    chart_main["column"] = {"values": column_values}
    chart_main["row"] = {"meta": row_meta, "values": row_values}


def _extract_titles(value: Any) -> list[str]:
    titles: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                walk(child)
            return

        if isinstance(node, dict):
            if "title" in node:
                titles.append(str(node.get("title")))
                return
            for child in node.values():
                walk(child)

    walk(value)
    return sorted(titles)


def _sorted_list(items: list[Any]) -> list[Any]:
    return sorted(items, key=_canonical)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
