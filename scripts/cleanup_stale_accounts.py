#!/usr/bin/env python3
"""Reconcile akahu_prod with the current Akahu account list.

After re-authorising a bank in Akahu, the connection often issues NEW `_id`
values for the same physical accounts. Because the main dlt ingest uses
``write_disposition='merge'`` keyed on `_id`, the old rows persist and you end
up with duplicates in the dashboard. This script:

1. Calls Akahu's /v1/accounts to get the authoritative current account IDs.
2. Lists every row in akahu_prod.accounts with its connection name + status,
   marking rows whose `_id` is no longer returned by Akahu as STALE.
3. With --apply, deletes the stale rows from akahu_prod.accounts,
   akahu_prod.account_balances, and akahu_prod.transactions (if present).

Default is dry-run; pass --apply to actually delete.

Usage:
    python scripts/cleanup_stale_accounts.py             # dry-run, diagnose
    python scripts/cleanup_stale_accounts.py --apply     # actually delete
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

import duckdb
import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.environ.get("DUCKDB_PATH") or os.path.join(ROOT, "data", "akahu.duckdb")


def _akahu_headers() -> Dict[str, str]:
    u = os.getenv("AKAHU_USER_TOKEN")
    a = os.getenv("AKAHU_APP_TOKEN")
    if not u or not a:
        raise SystemExit("Missing AKAHU_USER_TOKEN or AKAHU_APP_TOKEN in environment.")
    return {"Authorization": f"Bearer {u}", "X-Akahu-Id": a}


def _akahu_base_url() -> str:
    return os.getenv("AKAHU_API_URL", "https://api.akahu.io/v1").rstrip("/")


def fetch_live_accounts() -> List[Dict[str, Any]]:
    resp = requests.get(f"{_akahu_base_url()}/accounts", headers=_akahu_headers(), timeout=30)
    resp.raise_for_status()
    body = resp.json() or {}
    if isinstance(body, list):
        return body
    return body.get("items") or body.get("result") or []


def table_exists(conn: duckdb.DuckDBPyConnection, schema: str, name: str) -> bool:
    row = conn.execute(
        "select count(*) from information_schema.tables where table_schema=? and table_name=?",
        (schema, name),
    ).fetchone()
    return bool(row and row[0])


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true", help="Actually delete stale rows (default: dry-run)")
    p.add_argument("--db", default=DEFAULT_DB, help=f"DuckDB path (default: {DEFAULT_DB})")
    args = p.parse_args()

    if not os.path.exists(args.db):
        sys.exit(f"DuckDB not found at {args.db}")

    live = fetch_live_accounts()
    live_ids = {a["_id"] for a in live if a.get("_id")}

    print(f"Akahu /accounts returned {len(live)} live account(s):")
    for a in sorted(live, key=lambda x: ((x.get("connection") or {}).get("name") or "", x.get("name") or "")):
        conn_name = (a.get("connection") or {}).get("name") or "(none)"
        print(f"  [{a['_id']}]  conn={conn_name!r}  name={a.get('name')!r}  type={a.get('type')}  status={a.get('status')}")

    conn = duckdb.connect(args.db, read_only=not args.apply)

    print()
    print("Current rows in akahu_prod.accounts:")
    rows = conn.execute(
        """
        select _id, name, type, status, connection__name, _dlt_load_id
        from akahu_prod.accounts
        order by connection__name nulls first, name, _dlt_load_id
        """
    ).fetchall()
    for r in rows:
        marker = "      " if r[0] in live_ids else "STALE→"
        print(f"  {marker} [{r[0]}]  conn={r[4]!r}  name={r[1]!r}  type={r[2]}  status={r[3]}  load={r[5]}")

    stale_ids = [r[0] for r in rows if r[0] not in live_ids]
    print()
    if not stale_ids:
        print("✓ No stale rows to remove.")
        conn.close()
        return

    print(f"Found {len(stale_ids)} stale account row(s): {stale_ids}")

    if not args.apply:
        print("\n(Dry-run only — re-run with --apply to delete these rows from accounts,")
        print(" account_balances, and transactions.)")
        conn.close()
        return

    targets = [
        ("akahu_prod", "accounts", "_id"),
        ("akahu_prod", "account_balances", "account_id"),
        ("akahu_prod", "transactions", "_account"),
    ]
    placeholders = ",".join(["?"] * len(stale_ids))
    print("\nApplying deletes:")
    for schema, name, col in targets:
        if not table_exists(conn, schema, name):
            print(f"  - skipping {schema}.{name} (table does not exist)")
            continue
        before = conn.execute(
            f"select count(*) from {schema}.{name} where {col} in ({placeholders})",
            stale_ids,
        ).fetchone()[0]
        conn.execute(
            f"delete from {schema}.{name} where {col} in ({placeholders})",
            stale_ids,
        )
        print(f"  - deleted {before} row(s) from {schema}.{name}")

    conn.close()
    print("\n✓ Cleanup applied.")
    print("Next Dagster materialise will rebuild the dbt views off the cleaned data.")


if __name__ == "__main__":
    main()
