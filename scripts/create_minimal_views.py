#!/usr/bin/env python3
"""Create minimal DBT-like views/tables in the DuckDB used by the dashboard for local/dev runs.

This script is intended to be a convenience for development and testing: it creates
`stg_akahu_accounts`, `fct_account_daily_balances`, `fct_mortgage_over_time`, and
`dim_loan_accounts` derived from the mock `akahu_prod` schema produced by
`scripts/generate_mock_data.py`.

Run: python3 scripts/create_minimal_views.py
"""
import os
import duckdb


ROOT = os.path.dirname(os.path.dirname(__file__))
DB = os.path.join(ROOT, "data", "akahu.duckdb")


def main():
    if not os.path.exists(DB):
        raise SystemExit(f"DuckDB not found at {DB} - run scripts/generate_mock_data.py first")

    conn = duckdb.connect(DB)

    # stg_akahu_accounts: normalized view from akahu_prod.accounts
    conn.execute("""
    CREATE OR REPLACE VIEW stg_akahu_accounts AS
    SELECT
      _id AS account_id,
      name AS account_name,
      type AS account_type,
      CASE WHEN lower(coalesce(type,'')) LIKE '%credit%' OR lower(coalesce(type,'')) LIKE '%card%' THEN true ELSE false END AS is_credit_card,
      status,
      meta__loan_details__interest__rate AS loan_interest_rate,
      meta__loan_details__interest__type AS loan_interest_type,
      meta__loan_details__interest__expires_at AS loan_interest_expires_at,
      meta__loan_details__is_interest_only AS is_interest_only,
      meta__loan_details__term__years AS term_years,
      meta__loan_details__term__months AS term_months,
      meta__loan_details__matures_at AS loan_matures_at,
      meta__loan_details__initial_principal AS loan_initial_principal,
      meta__loan_details__repayment__frequency AS repayment_frequency,
      meta__loan_details__repayment__next_date AS repayment_next_date,
      meta__loan_details__repayment__next_amount AS repayment_next_amount,
      _dlt_load_id
    FROM akahu_prod.accounts
    """)

    # fct_account_daily_balances: convert strings to numeric where appropriate
    conn.execute("""
    CREATE OR REPLACE VIEW fct_account_daily_balances AS
    SELECT
      account_id,
      CAST(snapshot_date AS DATE) AS snapshot_date,
      TRY_CAST(current AS DOUBLE) AS current_balance,
      TRY_CAST(available AS DOUBLE) AS available_balance,
      TRY_CAST("limit" AS DOUBLE) AS credit_limit,
      currency,
      CASE WHEN lower(coalesce(account_type,'')) LIKE '%credit%' OR lower(coalesce(account_type,'')) LIKE '%card%' THEN true ELSE false END AS is_credit_card,
      account_type,
      coalesce(overdrawn, false) AS overdrawn,
      _dlt_load_id,
      TRY_CAST(snapshot_at AS TIMESTAMP) AS last_snapshot_at
    FROM akahu_prod.account_balances
    """)

    # fct_mortgage_over_time: aggregate per date
    conn.execute("""
    CREATE OR REPLACE VIEW fct_mortgage_over_time AS
    SELECT
      snapshot_date,
      SUM(CASE WHEN upper(coalesce(account_type,'')) = 'LOAN' THEN coalesce(TRY_CAST(current AS DOUBLE),0) ELSE 0 END) AS total_mortgage_balance,
      SUM(CASE WHEN lower(coalesce(account_type,'')) LIKE '%credit%' OR lower(coalesce(account_type,'')) LIKE '%card%' THEN coalesce(TRY_CAST(current AS DOUBLE),0) ELSE 0 END) AS total_creditcard_balance,
      SUM(coalesce(TRY_CAST(current AS DOUBLE),0)) AS total_net_debt,
      SUM(coalesce(TRY_CAST(available AS DOUBLE),0)) AS total_available,
      SUM(COALESCE(TRY_CAST("limit" AS DOUBLE),0)) AS total_limit
    FROM akahu_prod.account_balances
    GROUP BY snapshot_date
    ORDER BY snapshot_date
    """)

    # dim_loan_accounts: basic dim table with loan interest rate for loans only
    conn.execute("""
    CREATE OR REPLACE VIEW dim_loan_accounts AS
    SELECT
      account_id,
      loan_interest_rate::DOUBLE AS loan_interest_rate
    FROM stg_akahu_accounts
    WHERE upper(coalesce(account_type,'')) = 'LOAN'
    """)

    conn.close()
    print(f"Created development views in {DB}")


if __name__ == '__main__':
    main()
