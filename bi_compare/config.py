from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]
from typing import Any


@dataclass
class EnvConfig:
    name: str
    base_url: str
    domain: str
    login_id: str
    password: str
    page_token: str | None = None


@dataclass
class PagePairConfig:
    name: str
    left_page_id: str
    right_page_id: str
    card_mappings: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class SettingsConfig:
    timeout_seconds: int = 30
    max_diffs_per_card: int = 200
    match_cards_by: str = "name"
    request_view: str = "GRID"
    request_offset: int = 0
    request_limit: int = 20000
    request_filters: list[dict[str, Any]] = field(default_factory=list)
    request_dynamic_params: list[dict[str, Any]] = field(default_factory=list)
    compare_scope: str = "chartMain"
    ignore_paths: list[str] = field(default_factory=list)
    ignore_card_types: list[str] = field(default_factory=lambda: ["TEXT", "IFRAME", "PICTURE", "LAYOUT"])
    sort_arrays_before_compare: bool = False
    numeric_tolerance: float = 0.0


@dataclass
class CompareConfig:
    left: EnvConfig
    right: EnvConfig
    page_pairs: list[PagePairConfig]
    settings: SettingsConfig


def _resolve_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    if isinstance(value, str):
        return os.path.expandvars(value)
    return value


def _must_get(obj: dict[str, Any], key: str) -> Any:
    if key not in obj:
        raise ValueError(f"Missing required config key: {key}")
    return obj[key]


def load_config(path: str | Path) -> CompareConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")

    raw = tomllib.loads(p.read_text(encoding="utf-8"))
    raw = _resolve_env(raw)
    return build_config(raw)


def build_config(raw: dict[str, Any]) -> CompareConfig:
    raw = _resolve_env(raw)

    envs = _must_get(raw, "envs")
    left_raw = _must_get(envs, "prod")
    right_raw = _must_get(envs, "test")

    left = EnvConfig(
        name="prod",
        base_url=str(_must_get(left_raw, "base_url")).rstrip("/"),
        domain=str(_must_get(left_raw, "domain")),
        login_id=str(_must_get(left_raw, "login_id")),
        password=str(_must_get(left_raw, "password")),
        page_token=(str(left_raw["page_token"]).strip() if left_raw.get("page_token") else None),
    )
    right = EnvConfig(
        name="test",
        base_url=str(_must_get(right_raw, "base_url")).rstrip("/"),
        domain=str(_must_get(right_raw, "domain")),
        login_id=str(_must_get(right_raw, "login_id")),
        password=str(_must_get(right_raw, "password")),
        page_token=(str(right_raw["page_token"]).strip() if right_raw.get("page_token") else None),
    )

    settings_raw = raw.get("settings", {})
    settings = SettingsConfig(
        timeout_seconds=int(settings_raw.get("timeout_seconds", 30)),
        max_diffs_per_card=int(settings_raw.get("max_diffs_per_card", 200)),
        match_cards_by=str(settings_raw.get("match_cards_by", "name")),
        request_view=str(settings_raw.get("request_view", "GRID")),
        request_offset=int(settings_raw.get("request_offset", 0)),
        request_limit=int(settings_raw.get("request_limit", 20000)),
        request_filters=list(settings_raw.get("request_filters", [])),
        request_dynamic_params=list(settings_raw.get("request_dynamic_params", [])),
        compare_scope=str(settings_raw.get("compare_scope", "chartMain")),
        ignore_paths=list(settings_raw.get("ignore_paths", [])),
        ignore_card_types=list(
            settings_raw.get(
                "ignore_card_types",
                ["TEXT", "IFRAME", "PICTURE", "LAYOUT"],
            )
        ),
        sort_arrays_before_compare=bool(settings_raw.get("sort_arrays_before_compare", False)),
        numeric_tolerance=float(settings_raw.get("numeric_tolerance", 0.0)),
    )

    page_pairs: list[PagePairConfig] = []
    for i, pair_raw in enumerate(raw.get("page_pairs", [])):
        name = str(pair_raw.get("name", f"page_pair_{i + 1}"))
        left_page_id = str(_must_get(pair_raw, "prod_page_id"))
        right_page_id = str(_must_get(pair_raw, "test_page_id"))
        mappings: list[tuple[str, str]] = []
        for m in pair_raw.get("card_mappings", []):
            mappings.append((str(_must_get(m, "prod_card_id")), str(_must_get(m, "test_card_id"))))

        page_pairs.append(
            PagePairConfig(
                name=name,
                left_page_id=left_page_id,
                right_page_id=right_page_id,
                card_mappings=mappings,
            )
        )

    if not page_pairs:
        raise ValueError("No page_pairs configured")

    if settings.match_cards_by not in {"id", "name"}:
        raise ValueError("settings.match_cards_by must be 'id' or 'name'")
    if settings.request_view not in {"GRID", "GRAPH"}:
        raise ValueError("settings.request_view must be 'GRID' or 'GRAPH'")
    if settings.compare_scope not in {"chartMain", "full_response"}:
        raise ValueError("settings.compare_scope must be 'chartMain' or 'full_response'")

    return CompareConfig(left=left, right=right, page_pairs=page_pairs, settings=settings)
