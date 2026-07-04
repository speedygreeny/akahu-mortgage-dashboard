import csv
import io
import os
import duckdb
from datetime import date
from flask import Flask, jsonify, render_template, request, Response
from dotenv import load_dotenv
import logging

# Configure basic logging
logging.basicConfig(level=logging.DEBUG)

# Load environment variables from .env file.
load_dotenv()

# Initialize the Flask app
app = Flask(__name__)


def _parse_csv_env(name: str, default: set[str]) -> set[str]:
    raw = os.environ.get(name)
    if not raw:
        return set(default)
    return {v.strip() for v in raw.split(',') if v.strip()}


# Connections excluded from the mortgage dashboard (e.g. ASB business account
# that drives only the GST page). Override with EXCLUDED_CONNECTIONS=ASB,...
EXCLUDED_CONNECTIONS = _parse_csv_env('EXCLUDED_CONNECTIONS', {'ASB'})
# Connections used to populate the GST page account picker.
GST_CONNECTIONS = _parse_csv_env('GST_CONNECTIONS', {'ASB'})


# --- Database Connection ---
def get_db_connection():
    """Establishes a connection to the database."""
    # Try multiple likely locations for the DuckDB file:
    # 1. Environment variable DUCKDB_PATH
    # 2. repo-local ./data/akahu.duckdb (useful for local dev)
    # 3. container-mounted /data/akahu.duckdb (default in docker-compose)
    candidates = []
    env_path = os.environ.get('DUCKDB_PATH')
    if env_path:
        candidates.append(env_path)
    # repo-local data folder
    repo_data = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'akahu.duckdb')
    candidates.append(repo_data)
    # system/container path
    candidates.append('/data/akahu.duckdb')

    for path in candidates:
        try:
            if path and os.path.exists(path):
                logging.debug(f"Attempting to connect to DuckDB at {path}")
                conn = duckdb.connect(path, read_only=True)
                # detect schema once per successful connection
                try:
                    detect_schema(conn)
                except Exception:
                    # non-fatal: continue with default behavior
                    pass
                return conn
        except Exception as e:
            logging.error(f"Database connection attempt to {path} failed: {e}")

    logging.error(f"Database connection failed: none of candidate paths exist: {candidates}")
    return None


def find_existing_db_path():
    """Return the first existing candidate path or None."""
    env_path = os.environ.get('DUCKDB_PATH')
    repo_data = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'akahu.duckdb')
    candidates = [env_path] if env_path else []
    candidates.append(repo_data)
    candidates.append('/data/akahu.duckdb')
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


# module-level chosen schema prefix ('' | 'dbt' | 'akahu')
SCHEMA_PREFIX = None


def detect_schema(conn):
    """Set the module-level SCHEMA_PREFIX to the first matching schema that contains our expected tables.

    We check for 'dbt' then 'akahu' and fall back to empty string (no prefix).
    """
    global SCHEMA_PREFIX
    if SCHEMA_PREFIX is not None:
        return SCHEMA_PREFIX
    try:
        cur = conn.cursor()
        # check for dbt.fct_mortgage_over_time
        cur.execute("select count(*) from information_schema.tables where table_schema = 'dbt' and table_name = 'fct_mortgage_over_time'")
        row = cur.fetchone()
        if row and row[0] and int(row[0]) > 0:
            SCHEMA_PREFIX = 'dbt'
            cur.close()
            return SCHEMA_PREFIX

        # check for akahu.fct_mortgage_over_time
        cur.execute("select count(*) from information_schema.tables where table_schema = 'akahu' and table_name = 'fct_mortgage_over_time'")
        row = cur.fetchone()
        if row and row[0] and int(row[0]) > 0:
            SCHEMA_PREFIX = 'akahu'
            cur.close()
            return SCHEMA_PREFIX

        # fallback: no schema prefix
        SCHEMA_PREFIX = ''
        cur.close()
        return SCHEMA_PREFIX
    except Exception:
        # if anything goes wrong, leave prefix as empty to let unqualified names be used
        SCHEMA_PREFIX = ''
        try:
            cur.close()
        except Exception:
            pass
        return SCHEMA_PREFIX


def table(name: str) -> str:
    """Return a schema-qualified table name using detected SCHEMA_PREFIX.

    Example: table('fct_mortgage_over_time') -> 'dbt.fct_mortgage_over_time' (if prefix is 'dbt')
    """
    prefix = SCHEMA_PREFIX if SCHEMA_PREFIX is not None else ''
    if prefix:
        return f"{prefix}.{name}"
    return name


# --- Akahu finance APIs ---
@app.route('/api/akahu/accounts')
def akahu_accounts():
    """List all accounts (loans and credit cards) with details."""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Query from staging to get ALL accounts, then get latest version per account.
            # Filter out excluded connections (e.g. ASB business account driving GST only).
            excluded = list(EXCLUDED_CONNECTIONS)
            placeholders = ','.join(['?'] * len(excluded)) if excluded else ''
            exclude_clause = (
                f"and lower(coalesce(connection_name, '')) not in ({placeholders})"
                if excluded else ''
            )
            cur.execute(f"""
                with latest as (
                    select *,
                        row_number() over (partition by account_id order by _dlt_load_id desc) as rn
                    from {table('stg_akahu_accounts')}
                )
                select account_id, account_name, account_type, is_credit_card, status,
                    loan_interest_rate, loan_interest_type, loan_interest_expires_at,
                    is_interest_only, term_years, term_months,
                    loan_matures_at, loan_initial_principal,
                    repayment_frequency, repayment_next_date, repayment_next_amount
                from latest
                where rn = 1
                  {exclude_clause}
                order by account_name
            """, [c.lower() for c in excluded])
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.close()
            conn.close()
            return jsonify(rows)
        except Exception as e:
            logging.error(f"Error fetching akahu accounts: {e}")
            try:
                conn.close()
            except Exception:
                pass
            return jsonify({"error": "Failed to query database."}), 500
    return jsonify({"error": "Database connection failed"}), 500


@app.route('/api/akahu/account_balances/<account_id>')
def akahu_account_balances(account_id: str):
    """Daily balances for a specific account."""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Use '?' parameter style for duckdb
            cur.execute(f"""
                select snapshot_date, current_balance, available_balance, credit_limit, currency
                from {table('fct_account_daily_balances')}
                where account_id = ?
                order by snapshot_date
            """, (account_id,))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.close()
            conn.close()
            return jsonify(rows)
        except Exception as e:
            logging.error(f"Error fetching akahu account balances: {e}")
            try:
                conn.close()
            except Exception:
                pass
            return jsonify({"error": "Failed to query database."}), 500
    return jsonify({"error": "Database connection failed"}), 500


@app.route('/api/akahu/mortgage_over_time')
def akahu_mortgage_over_time():
    """Aggregated mortgage balance over time (sum over LOAN accounts)."""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(f"""
                select snapshot_date,
                       total_mortgage_balance,
                       total_creditcard_balance,
                       total_net_debt,
                       total_available,
                       total_limit
                from {table('fct_mortgage_over_time')}
                order by snapshot_date
            """)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.close()
            conn.close()
            return jsonify(rows)
        except Exception as e:
            logging.error(f"Error fetching akahu mortgage over time: {e}")
            try:
                conn.close()
            except Exception:
                pass
            return jsonify({"error": "Failed to query database."}), 500
    return jsonify({"error": "Database connection failed"}), 500


@app.route('/api/akahu/loan_kpis')
def akahu_loan_kpis():
    """KPI summary: total net-debt (mortgage + credit cards), change vs previous month, weighted interest rate on loans."""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(f"""
                with latest_date as (
                    select max(snapshot_date) as d from {table('fct_mortgage_over_time')}
                ), prev_date as (
                    select max(snapshot_date) as d
                    from {table('fct_mortgage_over_time')}, latest_date
                    where snapshot_date < date_trunc('month', (select d from latest_date))
                ), curr as (
                    select total_net_debt from {table('fct_mortgage_over_time')}
                    where snapshot_date = (select d from latest_date)
                ), prev as (
                    select total_net_debt from {table('fct_mortgage_over_time')}
                    where snapshot_date = (select d from prev_date)
                ), latest_bal as (
                    select distinct on (account_id)
                           account_id, current_balance
                    from {table('fct_account_daily_balances')}
                    where upper(coalesce(account_type,'')) = 'LOAN' and coalesce(is_credit_card,false) = false
                    order by account_id, snapshot_date desc, _dlt_load_id desc, last_snapshot_at desc
                ), weighted as (
                    select
                      sum(abs(b.current_balance)) as total_balance_pos,
                      case when sum(abs(b.current_balance)) > 0
                           then sum((l.loan_interest_rate)::numeric * abs(b.current_balance)) / sum(abs(b.current_balance))
                           else null end as weighted_rate
                    from {table('dim_loan_accounts')} l
                    join latest_bal b using (account_id)
                )
                select
                  abs(coalesce((select total_net_debt from curr), 0)) as total_net_debt,
                  abs(coalesce((select total_net_debt from curr), 0)) - abs(coalesce((select total_net_debt from prev), 0)) as monthly_change,
                  (select weighted_rate from weighted) as weighted_interest_rate
                """)
            row = cur.fetchone()
            cols = [d[0] for d in cur.description]
            result = dict(zip(cols, row)) if row else {}
            cur.close()
            conn.close()
            return jsonify(result)
        except Exception as e:
            logging.error(f"Error fetching akahu loan KPIs: {e}")
            try:
                conn.close()
            except Exception:
                pass
            return jsonify({"error": "Failed to query KPIs."}), 500
    return jsonify({"error": "Database connection failed"}), 500


# --- GST APIs ---
def _current_gst_period(today: date) -> tuple[date, date]:
    """Return start/end dates of NZ 2-monthly GST period containing today
    (Jan-Feb, Mar-Apr, May-Jun, Jul-Aug, Sep-Oct, Nov-Dec)."""
    from datetime import timedelta as _td
    start_month = today.month - ((today.month - 1) % 2)
    start = date(today.year, start_month, 1)
    end_month = start_month + 1
    end_year = today.year
    if end_month == 12:
        next_first = date(end_year + 1, 1, 1)
    else:
        next_first = date(end_year, end_month + 1, 1)
    end = next_first - _td(days=1)
    return start, end


def _has_transactions_view(conn) -> bool:
    cur = conn.cursor()
    prefix = SCHEMA_PREFIX or 'main'
    cur.execute(
        "select count(*) from information_schema.tables "
        "where table_schema = ? and table_name = 'stg_akahu_transactions'",
        (prefix,),
    )
    row = cur.fetchone()
    cur.close()
    return bool(row and row[0])


def _query_gst_transactions(conn, account_id: str, start: str, end: str):
    if not _has_transactions_view(conn):
        return [], None, None
    cur = conn.cursor()
    cur.execute(f"""
        select txn_date, txn_at, description, amount, balance, txn_type
        from {table('stg_akahu_transactions')}
        where account_id = ?
          and txn_date >= ?::date
          and txn_date <= ?::date
        order by txn_at, transaction_id
    """, (account_id, start, end))
    cols = [d[0] for d in cur.description]
    txns = [dict(zip(cols, r)) for r in cur.fetchall()]

    cur.execute(f"""
        select balance from {table('stg_akahu_transactions')}
        where account_id = ? and txn_date < ?::date and balance is not null
        order by txn_at desc, transaction_id desc limit 1
    """, (account_id, start))
    row = cur.fetchone()
    opening = float(row[0]) if row and row[0] is not None else None

    cur.execute(f"""
        select balance from {table('stg_akahu_transactions')}
        where account_id = ? and txn_date <= ?::date and balance is not null
        order by txn_at desc, transaction_id desc limit 1
    """, (account_id, end))
    row = cur.fetchone()
    closing = float(row[0]) if row and row[0] is not None else None

    # Fallback to stg_akahu_account_balances if a txn-level balance isn't available
    # (ASB is excluded from fct_account_daily_balances so we use the staging view
    # which still carries it).
    if opening is None or closing is None:
        cur.execute(f"""
            select snapshot_date, current_balance
            from {table('stg_akahu_account_balances')}
            where account_id = ? and current_balance is not null
            order by snapshot_date
        """, (account_id,))
        snaps = cur.fetchall()
        if opening is None:
            cand = [s for s in snaps if s[0] is not None and s[0] < date.fromisoformat(start)]
            if cand:
                opening = float(cand[-1][1])
        if closing is None:
            cand = [s for s in snaps if s[0] is not None and s[0] <= date.fromisoformat(end)]
            if cand:
                closing = float(cand[-1][1])

    cur.close()
    return txns, opening, closing


@app.route('/api/gst/accounts')
def gst_accounts():
    """Accounts available for GST (filtered to GST_CONNECTIONS, default ASB)."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    try:
        gst_conns = list(GST_CONNECTIONS)
        placeholders = ','.join(['?'] * len(gst_conns)) if gst_conns else "''"
        cur = conn.cursor()
        cur.execute(f"""
            with latest as (
                select *, row_number() over (partition by account_id order by _dlt_load_id desc) as rn
                from {table('stg_akahu_accounts')}
            )
            select account_id, account_name, account_type, connection_name, status
            from latest
            where rn = 1 and lower(coalesce(connection_name,'')) in ({placeholders})
            order by account_name
        """, [c.lower() for c in gst_conns])
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()
        return jsonify(rows)
    except Exception as e:
        logging.error(f"Error fetching GST accounts: {e}")
        return jsonify({"error": "Failed to query GST accounts."}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.route('/api/gst/transactions')
def gst_transactions():
    account_id = request.args.get('account_id')
    start = request.args.get('start')
    end = request.args.get('end')
    if not account_id or not start or not end:
        return jsonify({"error": "account_id, start, end are required"}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    try:
        txns, opening, closing = _query_gst_transactions(conn, account_id, start, end)
        inflow = sum(float(t['amount']) for t in txns if t['amount'] is not None and float(t['amount']) > 0)
        outflow = sum(float(t['amount']) for t in txns if t['amount'] is not None and float(t['amount']) < 0)
        return jsonify({
            "transactions": [{
                "txn_date": str(t['txn_date']) if t['txn_date'] is not None else None,
                "txn_at": t['txn_at'].isoformat() if t['txn_at'] is not None else None,
                "description": t['description'],
                "amount": float(t['amount']) if t['amount'] is not None else None,
                "balance": float(t['balance']) if t['balance'] is not None else None,
                "txn_type": t['txn_type'],
            } for t in txns],
            "opening_balance": opening,
            "closing_balance": closing,
            "totals": {
                "inflow": inflow,
                "outflow": outflow,
                "net": inflow + outflow,
                "count": len(txns),
            },
        })
    except Exception as e:
        logging.error(f"Error fetching GST transactions: {e}")
        return jsonify({"error": "Failed to query transactions."}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.route('/api/gst/transactions.csv')
def gst_transactions_csv():
    account_id = request.args.get('account_id')
    start = request.args.get('start')
    end = request.args.get('end')
    if not account_id or not start or not end:
        return Response("account_id, start, end are required", status=400)
    conn = get_db_connection()
    if not conn:
        return Response("Database connection failed", status=500)
    try:
        txns, opening, closing = _query_gst_transactions(conn, account_id, start, end)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['date', 'description', 'amount', 'balance', 'type'])
        for t in txns:
            writer.writerow([
                str(t['txn_date']) if t['txn_date'] is not None else '',
                t['description'] or '',
                f"{float(t['amount']):.2f}" if t['amount'] is not None else '',
                f"{float(t['balance']):.2f}" if t['balance'] is not None else '',
                t['txn_type'] or '',
            ])
        writer.writerow([])
        writer.writerow(['Opening balance', '', '', f"{opening:.2f}" if opening is not None else '', ''])
        writer.writerow(['Closing balance', '', '', f"{closing:.2f}" if closing is not None else '', ''])
        filename = f"gst_{account_id}_{start}_{end}.csv"
        return Response(buf.getvalue(), mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename="{filename}"'
        })
    except Exception as e:
        logging.error(f"Error generating GST CSV: {e}")
        return Response("Failed to generate CSV.", status=500)
    finally:
        try:
            conn.close()
        except Exception:
            pass


# --- Frontend Routes ---
@app.route('/')
def home():
    """Homepage with links to dashboards."""
    return render_template('home.html')


@app.route('/gst')
def gst():
    today = date.today()
    start, end = _current_gst_period(today)
    return render_template('gst.html', default_start=start.isoformat(), default_end=end.isoformat())


@app.route('/mortgage')
def mortgage():
    # Allow configuring house/property value via environment variable
    try:
        house_value = float(os.environ.get('HOUSE_VALUE')) if os.environ.get('HOUSE_VALUE') else 1450000.0
    except Exception:
        house_value = 1450000.0
    return render_template('mortgage.html', house_value=house_value)


@app.route('/health')
def health():
    """Health endpoint: reports DB path used and the latest snapshot_date if available."""
    # prefer using get_db_connection() so schema detection runs in the same place
    conn = get_db_connection()
    if not conn:
        return jsonify({"ok": False, "reason": "no_db_found", "candidates": [os.environ.get('DUCKDB_PATH'), os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'akahu.duckdb'), '/data/akahu.duckdb']}), 200

    # try to read the latest snapshot_date using schema-aware table names
    try:
        # ensure schema is detected for this connection
        try:
            detect_schema(conn)
        except Exception:
            pass
        cur = conn.cursor()
        cur.execute(f"select max(snapshot_date) as latest from {table('fct_mortgage_over_time')}")
        row = cur.fetchone()
        cur.close()
        # record path via find_existing_db_path (might be env or /data)
        path = find_existing_db_path()
        try:
            conn.close()
        except Exception:
            pass
        latest = row[0] if row and row[0] is not None else None
        return jsonify({"ok": True, "db_path": path, "latest_snapshot_date": str(latest) if latest is not None else None}), 200
    except Exception as e:
        logging.error(f"Health check DB query failed: {e}")
        path = find_existing_db_path()
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({"ok": False, "reason": "db_query_failed", "error": str(e), "db_path": path}), 200


# --- Main Execution ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8001, debug=True)
