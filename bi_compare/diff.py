from __future__ import annotations

from dataclasses import dataclass
from numbers import Number
from typing import Any


@dataclass
class DiffItem:
    path: str
    kind: str
    left: Any
    right: Any


def deep_diff(left: Any, right: Any, *, numeric_tolerance: float = 0.0, max_items: int = 200) -> list[DiffItem]:
    diffs: list[DiffItem] = []

    def walk(a: Any, b: Any, path: str) -> None:
        if len(diffs) >= max_items:
            return

        if type(a) is not type(b):
            diffs.append(DiffItem(path=path or "$", kind="type_changed", left=a, right=b))
            return

        if isinstance(a, dict):
            keys = sorted(set(a.keys()) | set(b.keys()))
            for key in keys:
                next_path = f"{path}.{key}" if path else key
                if key not in a:
                    diffs.append(DiffItem(path=next_path, kind="added", left=None, right=b[key]))
                    if len(diffs) >= max_items:
                        return
                    continue
                if key not in b:
                    diffs.append(DiffItem(path=next_path, kind="removed", left=a[key], right=None))
                    if len(diffs) >= max_items:
                        return
                    continue
                walk(a[key], b[key], next_path)
                if len(diffs) >= max_items:
                    return
            return

        if isinstance(a, list):
            if len(a) != len(b):
                diffs.append(DiffItem(path=path or "$", kind="length_changed", left=len(a), right=len(b)))
                if len(diffs) >= max_items:
                    return
            n = min(len(a), len(b))
            for i in range(n):
                walk(a[i], b[i], f"{path}[{i}]" if path else f"[{i}]")
                if len(diffs) >= max_items:
                    return
            return

        if isinstance(a, Number) and isinstance(b, Number):
            if abs(float(a) - float(b)) > numeric_tolerance:
                diffs.append(DiffItem(path=path or "$", kind="value_changed", left=a, right=b))
            return

        if a != b:
            diffs.append(DiffItem(path=path or "$", kind="value_changed", left=a, right=b))

    walk(left, right, path="")
    return diffs
