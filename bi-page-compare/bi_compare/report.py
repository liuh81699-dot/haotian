from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
from typing import Any


def write_reports(result: dict[str, Any], out_dir: str | Path) -> tuple[Path, Path]:
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)

    json_path = output / "compare_report.json"
    html_path = output / "compare_report.html"

    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    html_path.write_text(_to_html(result), encoding="utf-8")

    return json_path, html_path


def _to_html(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    pages = result.get("pages", [])

    page_sections = "\n".join(_render_page_section(page) for page in pages)

    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")

    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>BI 页面比对报告</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 24px; color: #1f2937; }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    .meta {{ color: #6b7280; margin-bottom: 16px; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 8px; margin-bottom: 20px; }}
    .box {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 12px; background: #f9fafb; }}
    .page {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; margin-bottom: 18px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 6px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f4f6; }}
    .status-equal {{ color: #047857; font-weight: 600; }}
    .status-different {{ color: #b91c1c; font-weight: 600; }}
    .status-error {{ color: #92400e; font-weight: 600; }}
    .small {{ font-size: 12px; color: #6b7280; }}
    details {{ margin-top: 4px; }}
    code {{ background: #f3f4f6; border-radius: 4px; padding: 1px 4px; }}
  </style>
</head>
<body>
  <h1>BI 页面比对报告</h1>
  <div class=\"meta\">生成时间: {html.escape(generated_at)}</div>

  <div class=\"summary\">
    <div class=\"box\"><strong>页面对数</strong><br>{summary.get('page_pairs', 0)}</div>
    <div class=\"box\"><strong>卡片比对数</strong><br>{summary.get('cards_compared', 0)}</div>
    <div class=\"box\"><strong>一致卡片</strong><br>{summary.get('cards_equal', 0)}</div>
    <div class=\"box\"><strong>差异卡片</strong><br>{summary.get('cards_different', 0)}</div>
    <div class=\"box\"><strong>错误卡片</strong><br>{summary.get('cards_error', 0)}</div>
    <div class=\"box\"><strong>prod独有 / test独有</strong><br>{summary.get('cards_prod_only', 0)} / {summary.get('cards_test_only', 0)}</div>
  </div>

  {page_sections}
</body>
</html>
"""


def _render_page_section(page: dict[str, Any]) -> str:
    summary = page.get("summary", {})
    warnings = page.get("warnings", [])
    errors = page.get("errors", [])
    cards = page.get("cards", [])

    warning_html = "".join(f"<li>{html.escape(str(w))}</li>" for w in warnings)
    error_html = "".join(f"<li>{html.escape(str(e))}</li>" for e in errors)

    cards_rows = "\n".join(_render_card_row(card) for card in cards)

    left_only = ", ".join(
        f"{c.get('name', '')} ({c.get('cdId', '')})" for c in page.get("left_only_cards", [])
    ) or "-"
    right_only = ", ".join(
        f"{c.get('name', '')} ({c.get('cdId', '')})" for c in page.get("right_only_cards", [])
    ) or "-"

    return f"""
<section class=\"page\">
  <h2>{html.escape(str(page.get('pair_name', '')))}</h2>
  <div class=\"small\">prod页面: <code>{html.escape(str(page.get('prod_page_id', '')))}</code> | test页面: <code>{html.escape(str(page.get('test_page_id', '')))}</code></div>
  <div class=\"small\">matched={summary.get('matched_cards', 0)}, different={summary.get('different_cards', 0)}, equal={summary.get('equal_cards', 0)}, error={summary.get('error_cards', 0)}</div>
  <div class=\"small\">prod独有卡片: {html.escape(left_only)}</div>
  <div class=\"small\">test独有卡片: {html.escape(right_only)}</div>

  {('<details><summary>Warnings</summary><ul>' + warning_html + '</ul></details>') if warnings else ''}
  {('<details><summary>Errors</summary><ul>' + error_html + '</ul></details>') if errors else ''}

  <table>
    <thead>
      <tr>
        <th>卡片</th>
        <th>prod_card_id</th>
        <th>test_card_id</th>
        <th>状态</th>
        <th>差异数</th>
        <th>示例差异</th>
      </tr>
    </thead>
    <tbody>
      {cards_rows}
    </tbody>
  </table>
</section>
"""


def _render_card_row(card: dict[str, Any]) -> str:
    status = str(card.get("status", ""))
    status_class = f"status-{status}"

    diffs = card.get("diffs", [])
    sample = "-"
    if diffs:
        top = diffs[0]
        sample = (
            f"{top.get('kind')} @ {top.get('path')} | "
            f"prod={_short_value(top.get('prod'))}, test={_short_value(top.get('test'))}"
        )

    if card.get("error"):
        sample = f"error: {card.get('error')}"

    return (
        "<tr>"
        f"<td>{html.escape(str(card.get('prod_card_name') or card.get('test_card_name') or ''))}</td>"
        f"<td><code>{html.escape(str(card.get('prod_card_id', '')))}</code></td>"
        f"<td><code>{html.escape(str(card.get('test_card_id', '')))}</code></td>"
        f"<td class=\"{html.escape(status_class)}\">{html.escape(status)}</td>"
        f"<td>{html.escape(str(card.get('diff_count', 0)))}</td>"
        f"<td>{html.escape(sample)}</td>"
        "</tr>"
    )


def _short_value(value: Any, limit: int = 80) -> str:
    text = json.dumps(value, ensure_ascii=False)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
