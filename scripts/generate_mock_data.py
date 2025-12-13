#!/usr/bin/env python3
"""
Generate mock Akahu data and populate data/akahu.duckdb.

This script will wipe the existing DuckDB file at data/akahu.duckdb (if present),
create a schema `akahu_prod` and two tables: `accounts` and `account_balances` to
match what the project's dbt models expect, then populate them with synthetic
data covering the last ~6 months of daily balances.

Usage: python3 scripts/generate_mock_data.py
"""
from __future__ import annotations
import os
import random
from datetime import datetime, timedelta, timezone, date
import json
import duckdb

ROOT = os.path.dirname(os.path.dirname(__file__))
DUCKDB_PATH = os.path.join(ROOT, "data", "akahu.duckdb")


def wipe_duckdb(path: str):
    if os.path.exists(path):
        print(f"Removing existing DuckDB at {path}")
        os.remove(path)


def create_tables(conn: duckdb.DuckDBPyConnection):
    # Create schema and raw tables that mimic dlt output
    conn.execute("CREATE SCHEMA IF NOT EXISTS akahu_prod")

    # accounts - keep many of the flattened meta__loan_details columns as text/numeric
    conn.execute(
        """
        CREATE TABLE akahu_prod.accounts (
            _id TEXT PRIMARY KEY,
            name TEXT,
            type TEXT,
            status TEXT,
            meta__loan_details__interest__rate DOUBLE,
            meta__loan_details__interest__type TEXT,
            meta__loan_details__interest__expires_at TIMESTAMPTZ,
            meta__loan_details__is_interest_only BOOLEAN,
            meta__loan_details__term__years INTEGER,
            meta__loan_details__term__months INTEGER,
            meta__loan_details__matures_at TIMESTAMPTZ,
            meta__loan_details__initial_principal DOUBLE,
            meta__loan_details__repayment__frequency TEXT,
            meta__loan_details__repayment__next_date TIMESTAMPTZ,
            meta__loan_details__repayment__next_amount DOUBLE,
            meta__loan_details__repayment__next_amount__v_double DOUBLE,
            _dlt_load_id TEXT
        )
        """
    )

    # account_balances - raw JSON-like for 'raw_balance' column we'll store as JSON string
    conn.execute(
        """
        CREATE TABLE akahu_prod.account_balances (
            account_id TEXT,
            snapshot_at TIMESTAMPTZ,
            snapshot_date DATE,
            account_name TEXT,
            account_type TEXT,
            connection_name TEXT,
            status TEXT,
            currency TEXT,
            current TEXT,
            available TEXT,
            "limit" TEXT,
            overdrawn BOOLEAN,
            refreshed_balance_at TIMESTAMPTZ,
            raw_balance TEXT,
            _dlt_load_id TEXT
        )
        """
    )


def generate_accounts() -> list[dict]:
    # create a handful of accounts including one mortgage/loan
    accounts = []
    now = datetime.now(timezone.utc)
    accounts.append({
        "_id": "acc_check_1",
        "name": "Everyday Checking",
        "type": "transaction",
        "status": "active",
        "meta__loan_details__initial_principal": None,
        "_dlt_load_id": "mock_load_1",
    })
    accounts.append({
        "_id": "acc_savings_1",
        "name": "Rainy Day Savings",
        "type": "savings",
        "status": "active",
        "_dlt_load_id": "mock_load_1",
    })
    accounts.append({
        "_id": "acc_credit_1",
        "name": "Rewards Credit",
        "type": "CREDITCARD",
        "status": "active",
        "_dlt_load_id": "mock_load_1",
    })
    # mortgage/loan account
    accounts.append({
        "_id": "acc_mortgage_1",
        "name": "Home Mortgage",
        "type": "LOAN",
        "status": "active",
        "meta__loan_details__interest__rate": 4.25,
        "meta__loan_details__interest__type": "fixed",
        "meta__loan_details__is_interest_only": False,
        "meta__loan_details__term__years": 30,
        "meta__loan_details__term__months": 0,
        "meta__loan_details__matures_at": (now.replace(year=now.year + 30)).isoformat(),
        "meta__loan_details__initial_principal": 600000.0,
        "meta__loan_details__repayment__frequency": "monthly",
        "meta__loan_details__repayment__next_date": (now + timedelta(days=30)).isoformat(),
        "meta__loan_details__repayment__next_amount": 3000.0,
        "meta__loan_details__repayment__next_amount__v_double": 3000.0,
        "_dlt_load_id": "mock_load_1",
    })

    return accounts


def generate_balances_for_account(account: dict, start_date: date, end_date: date) -> list[dict]:
    rows = []
    current = None
    acc_type = (account.get("type") or "")
    acc_type_l = acc_type.lower()
    # Seed starting balance per account type
    if "credit" in acc_type_l or "card" in acc_type_l:
        current = 1500.0
    elif "loan" in acc_type_l:
        # start mortgage at provided initial principal when available, otherwise fallback
        current = float(account.get("meta__loan_details__initial_principal") or 500000.0)
    elif "savings" in acc_type:
        current = 12000.0
    else:
        current = 2500.0

    date_iter = start_date
    # determine repayment schedule info for loans
    repayment_next_date_str = account.get("meta__loan_details__repayment__next_date")
    repayment_day = None
    try:
        if repayment_next_date_str:
            # parse ISO date/time and get day-of-month
            repayment_next_dt = datetime.fromisoformat(repayment_next_date_str)
            repayment_day = repayment_next_dt.day
    except Exception:
        repayment_day = None

    while date_iter <= end_date:
        # small random daily fluctuation for non-loans
        if "loan" in acc_type_l:
            # mortgages: accrue interest daily, and apply the whole monthly payment only on the repayment day
            monthly_payment = float(account.get("meta__loan_details__repayment__next_amount__v_double") or account.get("meta__loan_details__repayment__next_amount") or 3000.0)
            rate = float(account.get("meta__loan_details__interest__rate") or 0.0) / 100.0
            # daily interest accrual increases the balance
            interest = current * (rate / 365.0)
            current += interest
            # apply monthly payment only on the scheduled payment day
            pay_day = repayment_day or start_date.day
            if date_iter.day == pay_day:
                current -= monthly_payment
            # small symmetric noise to keep it looking natural
            current += random.uniform(-1, 1)
        else:
            daily_change = random.uniform(-200, 500)
            current = max(0.0, current + daily_change)

        # ensure we don't go negative
        if "loan" in acc_type_l:
            current = max(0.0, current)

        raw_balance = {
            "currency": "NZD",
            "current": current,
            "available": current if "loan" not in acc_type else None,
            "limit": None,
            "overdrawn": current < 0,
        }

        snapshot_at = datetime.combine(date_iter, datetime.min.time(), tzinfo=timezone.utc)

        rows.append({
            "account_id": account["_id"],
            "snapshot_at": snapshot_at.isoformat(),
            "snapshot_date": date_iter.isoformat(),
            "account_name": account.get("name"),
            "account_type": account.get("type"),
            "connection_name": "Mock Bank",
            "status": account.get("status"),
            "currency": raw_balance["currency"],
            "current": str(round(raw_balance["current"], 2)),
            "available": str(round(raw_balance["available"], 2)) if raw_balance["available"] is not None else None,
            "limit": None,
            "overdrawn": raw_balance["overdrawn"],
            "refreshed_balance_at": snapshot_at.isoformat(),
            "raw_balance": json.dumps(raw_balance),
            "_dlt_load_id": "mock_load_1",
        })

        date_iter += timedelta(days=1)

    return rows


def main():
    # Wipe DB
    wipe_duckdb(DUCKDB_PATH)

    os.makedirs(os.path.dirname(DUCKDB_PATH), exist_ok=True)

    conn = duckdb.connect(database=DUCKDB_PATH)
    create_tables(conn)

    accounts = generate_accounts()

    # insert accounts
    for acc in accounts:
        # prepare values (use duckdb parameterization)
        conn.execute(
            "INSERT INTO akahu_prod.accounts (" + 
            ", ".join(acc.keys()) + 
            ") VALUES (" + ",".join(["?" for _ in acc.keys()]) + ")",
            tuple(acc.values()),
        )

    # generate 6 months of daily balances up to today
    end_date = date.today()
    start_date = end_date - timedelta(days=180)

    total_rows = 0
    for acc in accounts:
        rows = generate_balances_for_account(acc, start_date, end_date)
        total_rows += len(rows)
        # batch insert
        cols = list(rows[0].keys())
        # quote any identifier that is a SQL keyword or contains special chars
        def quote_ident(c: str) -> str:
            if c.lower() in {"limit"} or not c.isidentifier():
                return '"' + c + '"'
            return c

        quoted_cols = [quote_ident(c) for c in cols]
        placeholders = ",".join(["?" for _ in cols])
        sql = f"INSERT INTO akahu_prod.account_balances ({', '.join(quoted_cols)}) VALUES ({placeholders})"
        params = [tuple(r[c] for c in cols) for r in rows]
        conn.executemany(sql, params)

    print(f"Inserted {len(accounts)} accounts and {total_rows} balance rows into {DUCKDB_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
