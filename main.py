from __future__ import annotations

import argparse
import sys

from bi_compare.config import load_config
from bi_compare.report import write_reports
from bi_compare.runner import run_compare


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare BI page card data between prod and test environments")
    parser.add_argument("--config", default="config.toml", help="Path to config file (TOML)")
    parser.add_argument("--out-dir", default="output", help="Output directory for reports")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        config = load_config(args.config)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] Load config failed: {e}", file=sys.stderr)
        return 1

    try:
        result = run_compare(config)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] Compare failed: {e}", file=sys.stderr)
        return 2

    json_path, html_path = write_reports(result, args.out_dir)
    summary = result.get("summary", {})

    print("Compare finished")
    print(f"- page_pairs: {summary.get('page_pairs', 0)}")
    print(f"- cards_compared: {summary.get('cards_compared', 0)}")
    print(f"- cards_equal: {summary.get('cards_equal', 0)}")
    print(f"- cards_different: {summary.get('cards_different', 0)}")
    print(f"- cards_error: {summary.get('cards_error', 0)}")
    print(f"- cards_prod_only: {summary.get('cards_prod_only', 0)}")
    print(f"- cards_test_only: {summary.get('cards_test_only', 0)}")
    print(f"- json_report: {json_path}")
    print(f"- html_report: {html_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
