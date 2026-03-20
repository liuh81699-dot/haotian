from __future__ import annotations

import copy
import fnmatch
import json
import math
from typing import Any

_SENTINEL = object()


def normalize_payload(
    payload: Any,
    *,
    ignore_paths: list[str],
    sort_arrays: bool,
    float_precision: int | None = None,
) -> Any:
    cloned = copy.deepcopy(payload)
    cleaned = _drop_ignored(cloned, path="", patterns=ignore_paths)
    if cleaned is _SENTINEL:
        cleaned = None
    normalized = _normalize_value(cleaned, sort_arrays=sort_arrays, float_precision=float_precision)
    return normalized


def _drop_ignored(value: Any, *, path: str, patterns: list[str]) -> Any:
    if _matches(path, patterns):
        return _SENTINEL

    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, child in value.items():
            child_path = key if not path else f"{path}.{key}"
            dropped = _drop_ignored(child, path=child_path, patterns=patterns)
            if dropped is not _SENTINEL:
                out[key] = dropped
        return out

    if isinstance(value, list):
        out_list: list[Any] = []
        for idx, child in enumerate(value):
            child_path = f"{path}[{idx}]" if path else f"[{idx}]"
            dropped = _drop_ignored(child, path=child_path, patterns=patterns)
            if dropped is not _SENTINEL:
                out_list.append(dropped)
        return out_list

    return value


def _normalize_value(value: Any, *, sort_arrays: bool, float_precision: int | None) -> Any:
    if isinstance(value, dict):
        return {k: _normalize_value(v, sort_arrays=sort_arrays, float_precision=float_precision) for k, v in sorted(value.items())}

    if isinstance(value, list):
        items = [_normalize_value(v, sort_arrays=sort_arrays, float_precision=float_precision) for v in value]
        if not sort_arrays:
            return items
        # Sorting arrays by canonical JSON makes order-insensitive comparisons possible when needed.
        return sorted(items, key=_canonical)

    if isinstance(value, float):
        if float_precision is None:
            return value
        if math.isnan(value) or math.isinf(value):
            return value
        return round(value, float_precision)

    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _matches(path: str, patterns: list[str]) -> bool:
    if not path:
        return False
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
    return False
