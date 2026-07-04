#!/usr/bin/env python3
"""One-off backfill of ASB transactions into ``akahu_prod.transactions``.

Uses Akahu's per-account endpoint ``GET /v1/accounts/{id}/transactions`` so we
pull *only* the ASB business account (not the global /transactions feed which
also returns ANZ/TSB). Writes via dlt with merge on ``_id`` so the rows dedupe
cleanly against future daily runs of the main pipeline.

Usage:
    python scripts/backfill_asb_transactions.py                       # last 3 months
    python scripts/backfill_asb_transactions.py --months 6
    python scripts/backfill_asb_transactions.py --start 2026-01-01 --end 2026-03-31
    python scripts/backfill_asb_transactions.py --account-id acc_xxxxxxx --months 3

Requires AKAHU_USER_TOKEN / AKAHU_APP_TOKEN in env (same as the main pipeline).
Auto-detection of the ASB account ID requires the main Dagster ingest to have
run at least once so ``akahu_prod.accounts`` exists.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional

import dlt
import duckdb
import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.environ.get("DUCKDB_PATH") or os.path.join(ROOT, "data", "akahu.duckdb")


def _akahu_headers() -> Dict[str, str]:
    user_token = os.getenv("AKAHU_USER_TOKEN")
    app_token = os.getenv("AKAHU_APP_TOKEN")
    if not user_token or not app_token:
        raise SystemExit("Missing AKAHU_USER_TOKEN or AKAHU_APP_TOKEN in environment.")
    return {"Authorization": f"Bearer {user_token}", "X-Akahu-Id": app_token}


def _akahu_base_url() -> str:
    return os.getenv("AKAHU_API_URL", "https://api.akahu.io/v1").rstrip("/")


def find_asb_account_ids(db_path: str) -> List[tuple[str, str]]:
    """Return [(account_id, account_name), ...] for ASB accounts in DuckDB."""
    if not os.path.exists(db_path):
        return []
    conn = duckdb.connect(db_path, read_only=True)
    try:
        rows = conn.execute(
            """
            with latest as (
                select _id, name, connection__name, _dlt_load_id,
                       row_number() over (partition by _id order by _dlt_load_id desc) as rn
                from akahu_prod.accounts
            )
            select _id, name from latest
            where rn = 1 and lower(coalesce(connection__name, '')) = 'asb'
            order by name
            """
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        conn.close()


def fetch_account_transactions(account_id: str, start_iso: str, end_iso: str) -> Iterator[Dict[str, Any]]:
    """Paginate ``/v1/accounts/{id}/transactions`` yielding one transaction at a time."""
    base = _akahu_base_url()
    headers = _akahu_headers()
    url = f"{base}/accounts/{account_id}/transactions"
    logger = logging.getLogger(__name__)
    cursor: Optional[str] = None
    page = 0
    total = 0
    while True:
        params: Dict[str, str] = {"start": start_iso, "end": end_iso}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        body = resp.json() or {}
        items = body.get("items") or []
        for item in items:
            if item and item.get("_id"):
                # Per-account endpoint may omit `_account`; the global endpoint
                # includes it, and the dbt staging model expects it.
                if not item.get("_account"):
                    item["_account"] = account_id
                yield item
                total += 1
        page += 1
        cursor = (body.get("cursor") or {}).get("next")
        if not cursor:
            break
    logger.info(
        "ASB transactions fetched: %d across %d page(s) (start=%s, end=%s)",
        total, page, start_iso, end_iso,
    )


@dlt.resource(name="transactions", write_disposition="merge", primary_key="_id")
def asb_transactions_resource(account_id: str, start_iso: str, end_iso: str) -> Iterator[Dict[str, Any]]:
    yield from fetch_account_transactions(account_id, start_iso, end_iso)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--account-id", help="ASB Akahu account ID (auto-detected from akahu_prod.accounts if omitted)")
    p.add_argument("--months", type=int, default=3, help="Number of months to backfill (default: 3)")
    p.add_argument("--start", help="ISO date YYYY-MM-DD (overrides --months)")
    p.add_argument("--end", help="ISO date YYYY-MM-DD (default: today, UTC)")
    p.add_argument("--db", default=DEFAULT_DB, help=f"DuckDB path (default: {DEFAULT_DB})")
    return p.parse_args()


def resolve_account_id(args: argparse.Namespace) -> str:
    if args.account_id:
        return args.account_id
    candidates = find_asb_account_ids(args.db)
    if not candidates:
        print(
            "No ASB account found in akahu_prod.accounts. Run the main Dagster ingest first "
            "to populate accounts, or pass --account-id explicitly.",
            file=sys.stderr,
        )
        sys.exit(1)
    if len(candidates) > 1:
        print("Multiple ASB accounts found; pass --account-id to choose:", file=sys.stderr)
        for acc_id, name in candidates:
            print(f"  {acc_id}  {name}", file=sys.stderr)
        sys.exit(2)
    acc_id, name = candidates[0]
    print(f"Auto-detected ASB account: {acc_id} ({name})")
    return acc_id


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv()
    args = parse_args()

    end_dt = (
        datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
        if args.end else datetime.now(timezone.utc)
    )
    start_dt = (
        datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
        if args.start else end_dt - timedelta(days=30 * args.months)
    )

    account_id = resolve_account_id(args)
    start_iso = start_dt.isoformat()
    end_iso = end_dt.isoformat()
    print(f"Backfilling ASB transactions: {start_iso} → {end_iso}  db={args.db}")

    # Use a dedicated pipeline_name so the backfill's dlt state is isolated from
    # the daily `akahu_finance_daily` pipeline. We write to the same dataset and
    # table; merge on _id keeps it idempotent across both pipelines.
    pipeline = dlt.pipeline(
        pipeline_name="akahu_asb_backfill",
        destination=dlt.destinations.duckdb(args.db),
        dataset_name="akahu_prod",
    )
    info = pipeline.run(asb_transactions_resource(account_id, start_iso, end_iso))
    print(info)


if __name__ == "__main__":
    main()
