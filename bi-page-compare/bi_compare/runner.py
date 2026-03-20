from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .client import ApiError, BiApiClient
from .compare_rules import apply_chart_compare_rules
from .config import CompareConfig, PagePairConfig, SettingsConfig
from .diff import deep_diff
from .normalize import normalize_payload

ProgressCallback = Callable[[dict], None]
StopChecker = Callable[[], bool]


class CompareCancelled(RuntimeError):
    pass


@dataclass
class _PreparedPage:
    page_result: dict[str, Any]
    matches: list[tuple[dict[str, Any], dict[str, Any]]]


def run_compare(
    config: CompareConfig,
    *,
    on_progress: ProgressCallback | None = None,
    should_stop: StopChecker | None = None,
) -> dict[str, Any]:
    left_client = BiApiClient(config.left, timeout_seconds=config.settings.timeout_seconds)
    right_client = BiApiClient(config.right, timeout_seconds=config.settings.timeout_seconds)

    _check_cancel(should_stop)
    _emit_progress(
        on_progress,
        stage="sign_in",
        message="Signing in",
        processed_cards=0,
        total_cards=0,
        processed_page_pairs=0,
        total_page_pairs=len(config.page_pairs),
    )

    # If both sides use the same endpoint + account, reuse one sign-in token in this run.
    if _same_signin_identity(config):
        shared_token = left_client.sign_in()
        right_client.token = shared_token
    else:
        left_client.sign_in()
        right_client.sign_in()

    total_cards_compared = 0
    total_cards_diff = 0
    total_cards_equal = 0
    total_cards_error = 0
    total_cards_left_only = 0
    total_cards_right_only = 0
    total_page_errors = 0

    prepared_pages: list[_PreparedPage] = []
    total_cards_planned = 0

    for pair_index, pair in enumerate(config.page_pairs, start=1):
        _check_cancel(should_stop)
        _emit_progress(
            on_progress,
            stage="prepare_pages",
            message=f"Preparing page pair: {pair.name}",
            current_pair_name=pair.name,
            processed_cards=0,
            total_cards=total_cards_planned,
            processed_page_pairs=pair_index - 1,
            total_page_pairs=len(config.page_pairs),
        )

        page_result = {
            "pair_name": pair.name,
            "prod_page_id": pair.left_page_id,
            "test_page_id": pair.right_page_id,
            "status": "ok",
            "errors": [],
            "warnings": [],
            "summary": {},
            "cards": [],
            "left_only_cards": [],
            "right_only_cards": [],
        }

        matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
        try:
            left_page = left_client.get_page(pair.left_page_id)
            right_page = right_client.get_page(pair.right_page_id)

            left_cards = _filter_cards(left_page.get("cards", []), config.settings)
            right_cards = _filter_cards(right_page.get("cards", []), config.settings)

            matches, left_only, right_only, warnings = _match_cards(pair, left_cards, right_cards, config.settings)
            page_result["warnings"].extend(warnings)
            page_result["left_only_cards"] = left_only
            page_result["right_only_cards"] = right_only

            total_cards_left_only += len(left_only)
            total_cards_right_only += len(right_only)
            total_cards_planned += len(matches)

        except ApiError as e:
            page_result["status"] = "error"
            page_result["errors"].append(str(e))
            total_page_errors += 1

        prepared_pages.append(_PreparedPage(page_result=page_result, matches=matches))

        _emit_progress(
            on_progress,
            stage="prepare_pages",
            message=f"Prepared page pair: {pair.name}",
            current_pair_name=pair.name,
            processed_cards=0,
            total_cards=total_cards_planned,
            processed_page_pairs=pair_index,
            total_page_pairs=len(config.page_pairs),
        )

    pages: list[dict[str, Any]] = []
    request_body = _build_card_request(config.settings)
    processed_cards = 0

    for page_index, prepared in enumerate(prepared_pages, start=1):
        _check_cancel(should_stop)
        page_result = prepared.page_result

        if page_result["status"] == "error":
            page_result["summary"] = {
                "matched_cards": 0,
                "different_cards": 0,
                "equal_cards": 0,
                "error_cards": 0,
                "left_only_cards": len(page_result["left_only_cards"]),
                "right_only_cards": len(page_result["right_only_cards"]),
            }
            pages.append(page_result)
            continue

        matches = prepared.matches
        for left_card, right_card in matches:
            _check_cancel(should_stop)
            _emit_progress(
                on_progress,
                stage="compare_cards",
                message=f"Comparing card: {left_card.get('name') or left_card.get('cdId')}",
                current_pair_name=page_result["pair_name"],
                processed_cards=processed_cards,
                total_cards=total_cards_planned,
                processed_page_pairs=page_index,
                total_page_pairs=len(config.page_pairs),
            )

            total_cards_compared += 1
            card_result = {
                "prod_card_id": left_card.get("cdId"),
                "test_card_id": right_card.get("cdId"),
                "prod_card_name": left_card.get("name"),
                "test_card_name": right_card.get("name"),
                "status": "equal",
                "diff_count": 0,
                "diffs": [],
            }

            try:
                left_data = left_client.get_card_data(str(left_card.get("cdId")), body=request_body)
                right_data = right_client.get_card_data(str(right_card.get("cdId")), body=request_body)

                left_scope = _pick_scope(left_data, config.settings)
                right_scope = _pick_scope(right_data, config.settings)
                left_scope = apply_chart_compare_rules(left_scope, scope=config.settings.compare_scope)
                right_scope = apply_chart_compare_rules(right_scope, scope=config.settings.compare_scope)

                left_normalized = normalize_payload(
                    left_scope,
                    ignore_paths=config.settings.ignore_paths,
                    sort_arrays=config.settings.sort_arrays_before_compare,
                    float_precision=None,
                )
                right_normalized = normalize_payload(
                    right_scope,
                    ignore_paths=config.settings.ignore_paths,
                    sort_arrays=config.settings.sort_arrays_before_compare,
                    float_precision=None,
                )

                diffs = deep_diff(
                    left_normalized,
                    right_normalized,
                    numeric_tolerance=config.settings.numeric_tolerance,
                    max_items=config.settings.max_diffs_per_card,
                )
                card_result["diff_count"] = len(diffs)
                card_result["diffs"] = [
                    {
                        "path": d.path,
                        "kind": d.kind,
                        "prod": d.left,
                        "test": d.right,
                    }
                    for d in diffs
                ]
                if diffs:
                    card_result["status"] = "different"
                    total_cards_diff += 1
                else:
                    total_cards_equal += 1

            except ApiError as e:
                card_result["status"] = "error"
                card_result["error"] = str(e)
                total_cards_error += 1

            page_result["cards"].append(card_result)
            processed_cards += 1

            _emit_progress(
                on_progress,
                stage="compare_cards",
                message=f"Compared card: {left_card.get('name') or left_card.get('cdId')}",
                current_pair_name=page_result["pair_name"],
                processed_cards=processed_cards,
                total_cards=total_cards_planned,
                processed_page_pairs=page_index,
                total_page_pairs=len(config.page_pairs),
            )

        page_result["summary"] = {
            "matched_cards": len(matches),
            "different_cards": sum(1 for c in page_result["cards"] if c["status"] == "different"),
            "equal_cards": sum(1 for c in page_result["cards"] if c["status"] == "equal"),
            "error_cards": sum(1 for c in page_result["cards"] if c["status"] == "error"),
            "left_only_cards": len(page_result["left_only_cards"]),
            "right_only_cards": len(page_result["right_only_cards"]),
        }

        pages.append(page_result)

    result_status = _resolve_result_status(
        cards_different=total_cards_diff,
        cards_prod_only=total_cards_left_only,
        cards_test_only=total_cards_right_only,
        cards_error=total_cards_error,
        page_errors=total_page_errors,
    )

    result = {
        "summary": {
            "page_pairs": len(config.page_pairs),
            "cards_compared": total_cards_compared,
            "cards_equal": total_cards_equal,
            "cards_different": total_cards_diff,
            "cards_error": total_cards_error,
            "cards_prod_only": total_cards_left_only,
            "cards_test_only": total_cards_right_only,
            "page_errors": total_page_errors,
            "result_status": result_status,
        },
        "pages": pages,
    }

    _emit_progress(
        on_progress,
        stage="done",
        message="Comparison completed",
        processed_cards=processed_cards,
        total_cards=total_cards_planned,
        processed_page_pairs=len(config.page_pairs),
        total_page_pairs=len(config.page_pairs),
    )

    return result


def _check_cancel(should_stop: StopChecker | None) -> None:
    if should_stop and should_stop():
        raise CompareCancelled("Comparison cancelled by user")


def _emit_progress(on_progress: ProgressCallback | None, **payload: Any) -> None:
    if on_progress:
        on_progress(payload)


def _resolve_result_status(
    *,
    cards_different: int,
    cards_prod_only: int,
    cards_test_only: int,
    cards_error: int,
    page_errors: int,
) -> str:
    if cards_error > 0 or page_errors > 0:
        return "exception"
    if cards_different > 0 or cards_prod_only > 0 or cards_test_only > 0:
        return "inconsistent"
    return "consistent"


def _same_signin_identity(config: CompareConfig) -> bool:
    return (
        config.left.base_url == config.right.base_url
        and config.left.domain == config.right.domain
        and config.left.login_id == config.right.login_id
        and config.left.password == config.right.password
    )


def _filter_cards(cards: Any, settings: SettingsConfig) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        cd_type = str(card.get("cdType", ""))
        if cd_type in settings.ignore_card_types:
            continue
        if "cdId" not in card:
            continue
        out.append(card)
    return out


def _match_cards(
    pair: PagePairConfig,
    left_cards: list[dict[str, Any]],
    right_cards: list[dict[str, Any]],
    settings: SettingsConfig,
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []

    left_by_id = {str(c.get("cdId")): c for c in left_cards}
    right_by_id = {str(c.get("cdId")): c for c in right_cards}

    if pair.card_mappings:
        used_left: set[str] = set()
        used_right: set[str] = set()
        for left_id, right_id in pair.card_mappings:
            left_card = left_by_id.get(left_id)
            right_card = right_by_id.get(right_id)
            if not left_card or not right_card:
                warnings.append(f"Explicit mapping missing: prod={left_id}, test={right_id}")
                continue
            matches.append((left_card, right_card))
            used_left.add(left_id)
            used_right.add(right_id)

        left_only = [c for cid, c in left_by_id.items() if cid not in used_left]
        right_only = [c for cid, c in right_by_id.items() if cid not in used_right]
        return matches, left_only, right_only, warnings

    if settings.match_cards_by == "id":
        shared_ids = sorted(set(left_by_id.keys()) & set(right_by_id.keys()))
        shared_id_set = set(shared_ids)
        for card_id in shared_ids:
            matches.append((left_by_id[card_id], right_by_id[card_id]))
        left_only = [c for cid, c in left_by_id.items() if cid not in shared_id_set]
        right_only = [c for cid, c in right_by_id.items() if cid not in shared_id_set]
        return matches, left_only, right_only, warnings

    left_name_index: dict[str, list[dict[str, Any]]] = {}
    right_name_index: dict[str, list[dict[str, Any]]] = {}

    for card in left_cards:
        name = _normalize_name(card.get("name"))
        left_name_index.setdefault(name, []).append(card)
    for card in right_cards:
        name = _normalize_name(card.get("name"))
        right_name_index.setdefault(name, []).append(card)

    used_left: set[str] = set()
    used_right: set[str] = set()

    for name in sorted(set(left_name_index.keys()) & set(right_name_index.keys())):
        l_group = left_name_index[name]
        r_group = right_name_index[name]

        if len(l_group) != 1 or len(r_group) != 1:
            warnings.append(
                f"Card name '{name}' is not unique (prod={len(l_group)}, test={len(r_group)}), skipped"
            )
            continue

        l_card = l_group[0]
        r_card = r_group[0]
        matches.append((l_card, r_card))
        used_left.add(str(l_card.get("cdId")))
        used_right.add(str(r_card.get("cdId")))

    left_only = [c for c in left_cards if str(c.get("cdId")) not in used_left]
    right_only = [c for c in right_cards if str(c.get("cdId")) not in used_right]
    return matches, left_only, right_only, warnings


def _normalize_name(name: Any) -> str:
    return str(name or "").strip()


def _build_card_request(settings: SettingsConfig) -> dict[str, Any]:
    body: dict[str, Any] = {
        "view": settings.request_view,
        "offset": settings.request_offset,
        "limit": settings.request_limit,
    }
    if settings.request_dynamic_params:
        body["dynamicParams"] = settings.request_dynamic_params
    if settings.request_filters:
        body["filters"] = settings.request_filters
    return body


def _pick_scope(response: dict[str, Any], settings: SettingsConfig) -> Any:
    if settings.compare_scope == "full_response":
        return response
    chart_main = response.get("chartMain")
    if chart_main is None:
        return response
    return chart_main
