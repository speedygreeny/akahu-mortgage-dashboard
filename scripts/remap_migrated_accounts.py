#!/usr/bin/env python3
"""Remap re-authorised Akahu accounts using Akahu's ``_migrated`` field.

When you re-auth a connection in Akahu, the new account row often gets a fresh
internal ``_id``. Akahu records the prior ``_id`` in the new row's
``_migrated`` column. This script reads those pairs and rewrites the
``account_id`` references on every historical balance and transaction row,
then drops only the now-empty stale metadata row from ``akahu_prod.accounts``.

**No balance or transaction data is deleted.** Only the duplicate metadata row
in ``akahu_prod.accounts`` (which produces the duplicate account card in the
dashboard) is removed, after the references on history have been remapped to
the new ``_id``.

Default is dry-run; pass ``--apply`` to execute.

Usage:
    python scripts/remap_migrated_accounts.py
    python scripts/remap_migrated_accounts.py --db /home/ubuntu/home-data-platform/data/akahu.duckdb
    python scripts/remap_migrated_accounts.py --db ... --apply
    python scripts/remap_migrated_accounts.py --map old_id=new_id --apply    # manual override

The ``--map`` flag is for the rare case where Akahu didn't set ``_migrated``
(e.g. you have a manual mapping in mind). It is additive on top of the
automatic detection.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.environ.get("DUCKDB_PATH") or os.path.join(ROOT, "data", "akahu.duckdb")


def table_exists(conn: duckdb.DuckDBPyConnection, schema: str, name: str) -> bool:
    row = conn.execute(
        "select count(*) from information_schema.tables where table_schema=? and table_name=?",
        (schema, name),
    ).fetchone()
    return bool(row and row[0])


def column_exists(conn: duckdb.DuckDBPyConnection, schema: str, table: str, col: str) -> bool:
    row = conn.execute(
        "select count(*) from information_schema.columns "
        "where table_schema=? and table_name=? and column_name=?",
        (schema, table, col),
    ).fetchone()
    return bool(row and row[0])


def describe(conn: duckdb.DuckDBPyConnection, account_id: str) -> str:
    row = conn.execute(
        "select connection__name, name, type, balance__current "
        "from akahu_prod.accounts where _id = ?",
        (account_id,),
    ).fetchone()
    if not row:
        return "(not in akahu_prod.accounts)"
    cn, nm, tp, bal = row
    return f"{cn or '?'} {nm or '?'} ({tp or '?'}, balance={bal})"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=DEFAULT_DB, help=f"DuckDB path (default: {DEFAULT_DB})")
    p.add_argument("--apply", action="store_true", help="Actually apply the remap (default: dry-run)")
    p.add_argument(
        "--map", action="append", default=[], metavar="OLD=NEW",
        help="Manual remap pair, in addition to _migrated-based detection (repeatable)",
    )
    args = p.parse_args()

    if not os.path.exists(args.db):
        sys.exit(f"DuckDB not found at {args.db}")

    print(f"DB: {args.db}")
    conn = duckdb.connect(args.db, read_only=not args.apply)

    if not table_exists(conn, "akahu_prod", "accounts"):
        sys.exit("akahu_prod.accounts not found; nothing to remap.")

    mapping: Dict[str, str] = {}
    if column_exists(conn, "akahu_prod", "accounts", "_migrated"):
        rows = conn.execute(
            "select _migrated, _id from akahu_prod.accounts where _migrated is not null"
        ).fetchall()
        for old, new in rows:
            mapping[old] = new
        print(f"Detected from _migrated: {len(mapping)} pair(s)")
    else:
        print("(_migrated column not present — automatic detection skipped)")

    for entry in args.map:
        if "=" not in entry:
            sys.exit(f"--map expects OLD=NEW, got {entry!r}")
        old, new = (s.strip() for s in entry.split("=", 1))
        mapping[old] = new
    if args.map:
        print(f"After --map overrides: {len(mapping)} pair(s)")

    if not mapping:
        print("Nothing to remap. Done.")
        conn.close()
        return

    has_transactions = table_exists(conn, "akahu_prod", "transactions")

    print("\nPlanned remap (old → new):")
    plans = []
    for old, new in mapping.items():
        bal_count = conn.execute(
            "select count(*) from akahu_prod.account_balances where account_id = ?", (old,)
        ).fetchone()[0]
        txn_count = (
            conn.execute(
                "select count(*) from akahu_prod.transactions where _account = ?", (old,)
            ).fetchone()[0]
            if has_transactions else 0
        )
        print(f"  {old}  ({describe(conn, old)})")
        print(f"  → {new}  ({describe(conn, new)})")
        print(f"     remap: {bal_count} balance row(s), {txn_count} transaction row(s)\n")
        plans.append((old, new, bal_count, txn_count))

    if not args.apply:
        print("(Dry-run — re-run with --apply to execute.)")
        conn.close()
        return

    total_bal = total_txn = total_meta = 0
    for old, new, _, _ in plans:
        conn.execute(
            "update akahu_prod.account_balances set account_id = ? where account_id = ?",
            (new, old),
        )
        # Capture rowcount via a re-count delta is tricky in DuckDB; use the planned count instead.
        if has_transactions:
            conn.execute(
                "update akahu_prod.transactions set _account = ? where _account = ?",
                (new, old),
            )
        meta_n = conn.execute(
            "select count(*) from akahu_prod.accounts where _id = ?", (old,)
        ).fetchone()[0]
        conn.execute("delete from akahu_prod.accounts where _id = ?", (old,))
        total_meta += meta_n

    for _, _, bal_count, txn_count in plans:
        total_bal += bal_count
        total_txn += txn_count

    print(
        f"✓ Remap applied. {total_bal} balance row(s) repointed, "
        f"{total_txn} transaction row(s) repointed, "
        f"{total_meta} stale account metadata row(s) removed."
    )
    print("Trigger the next Dagster materialise to rebuild the dbt views off the cleaned data.")
    conn.close()


if __name__ == "__main__":
    main()
