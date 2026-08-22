from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from .api import audit_tushare_company
from .contracts import TushareAdapterError


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be YYYY-MM-DD") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="value-audit-tushare",
        description="Run a point-in-time value audit from Tushare rows.",
    )
    parser.add_argument("ticker")
    parser.add_argument("--as-of", type=_date, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--token",
        help=(
            "Tushare token. Prefer TUSHARE_TOKEN to avoid command history and "
            "process-list exposure."
        ),
    )
    parser.add_argument("--history-years", type=int, default=12)
    parser.add_argument(
        "--company-type",
        choices=("auto", "financial", "non-financial"),
        default="auto",
        help=(
            "Override current stock_basic industry classification for "
            "point-in-time audits."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = audit_tushare_company(
            args.ticker,
            args.as_of,
            token=args.token,
            history_years=args.history_years,
            is_financial=(
                None
                if args.company_type == "auto"
                else args.company_type == "financial"
            ),
        )
    except (TushareAdapterError, ValueError) as error:
        print(f"error: {error}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
