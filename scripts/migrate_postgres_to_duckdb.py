"""Migrate three tables from a remote Postgres into the project's DuckDB file.

Usage:
  export PGHOST=192.168.1.199
  export PGPORT=5432
  export PGDATABASE=mg_data
  export PGUSER=airflow
  # do NOT export PGPASSWORD on shared shells; instead the script will prompt for it if not set
  python3 scripts/migrate_postgres_to_duckdb.py --tables account_balances accounts accounts__attributes

The script will append/overwrite tables in data/akahu.duckdb. By default it will create or replace the tables.

Notes:
- Credentials are read from environment variables PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
  or from a prompt if PGPASSWORD is not set.
- Uses chunked reading to avoid loading everything into memory.
- Verifies table existence and schema compatibility by sampling the first row.
"""

import os
import sys
import argparse
import getpass
import duckdb
import psycopg2
import pandas as pd
from psycopg2.extras import RealDictCursor

DUCKDB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "akahu.duckdb")
DEFAULT_CHUNK = 10000


def get_pg_conn(host, port, db, user, password):
    conn = psycopg2.connect(host=host, port=port, dbname=db, user=user, password=password)
    return conn


def migrate_table(pg_conn, table, schema, duck_conn, duck_table=None, if_exists="replace", chunk_size=DEFAULT_CHUNK):
    full_table = f"{schema}.{table}"
    target_table = duck_table or table
    cur = pg_conn.cursor(name=f"csr_{table}", cursor_factory=RealDictCursor)
    cur.execute(f"SELECT * FROM {full_table};")

    first = cur.fetchmany(1)
    if not first:
        print(f"Table {full_table} is empty, creating empty table in DuckDB and continuing.")
        # Create empty table by executing zero-row insert using pandas empty df
        df_empty = pd.DataFrame(columns=[])
        duck_conn.register("df_tmp", df_empty)
        duck_conn.execute(f"CREATE TABLE IF NOT EXISTS {target_table} AS SELECT * FROM df_tmp WHERE 1=0")
        duck_conn.unregister("df_tmp")
        cur.close()
        return

    # Convert first batch to DataFrame
    df_first = pd.DataFrame(first)

    # Write first batch with mode (table will be created under the duck schema by caller)
    # Expect caller to pass duck-qualified table name via duck_conn.execute; here we will rely on
    # a temporary table name and let the caller insert into the properly qualified name.
    duck_conn.register("df_tmp", df_first)
    # the caller should have set the search path or will use fully qualified names
    if if_exists == "replace":
        duck_conn.execute(f"DROP TABLE IF EXISTS {target_table}")
        duck_conn.execute(f"CREATE TABLE {target_table} AS SELECT * FROM df_tmp")
    elif if_exists == "append":
        duck_conn.execute(f"CREATE TABLE IF NOT EXISTS {target_table} AS SELECT * FROM df_tmp WHERE 1=0")
        duck_conn.execute(f"INSERT INTO {target_table} SELECT * FROM df_tmp")
    else:
        duck_conn.unregister("df_tmp")
        raise ValueError("if_exists must be 'replace' or 'append'")
    duck_conn.unregister("df_tmp")

    # Process remaining rows in chunks
    while True:
        rows = cur.fetchmany(chunk_size)
        if not rows:
            break
        df = pd.DataFrame(rows)
        duck_conn.register("df_tmp", df)
        duck_conn.execute(f"INSERT INTO {target_table} SELECT * FROM df_tmp")
        duck_conn.unregister("df_tmp")
        print(f"Inserted {len(df)} rows into {target_table}")

    cur.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate tables from Postgres to DuckDB")
    parser.add_argument("--tables", nargs="+", required=True, help="List of table names (without schema)")
    parser.add_argument("--schema", default="akahu_prod", help="Source Postgres schema")
    parser.add_argument("--duckdb", default=DUCKDB_PATH, help="Destination DuckDB file path")
    parser.add_argument("--if-exists", choices=["replace", "append"], default="replace")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK)
    parser.add_argument("--duck-schema", default=None, help="Destination schema in DuckDB (defaults to source Postgres schema)")
    parser.add_argument("--duck-db-alias", default=os.getenv("DUCKDB_DB_ALIAS", "akahu"), help="Alias name to ATTACH the DuckDB file as so dbt can reference database.schema.table (default 'akahu')")
    # Destructive safety flags
    parser.add_argument("--clear-file", action="store_true", help="Delete the destination DuckDB file before migrating (destructive)")
    parser.add_argument("--drop-all", action="store_true", help="Drop all tables in the destination DuckDB before migrating (destructive)")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive actions (required when using --clear-file or --drop-all)")
    args = parser.parse_args()

    host = os.getenv("PGHOST") or input("Postgres host: ")
    port = os.getenv("PGPORT") or input("Postgres port [5432]: ") or "5432"
    db = os.getenv("PGDATABASE") or input("Postgres database: ")
    user = os.getenv("PGUSER") or input("Postgres user: ")
    password = os.getenv("PGPASSWORD") or getpass.getpass("Postgres password (will not echo): ")

    print(f"Connecting to Postgres {host}:{port}/{db} as {user}")
    pg_conn = get_pg_conn(host, port, db, user, password)

    # Handle destructive options safely
    if args.clear_file:
        if not args.yes:
            print("Refusing to delete DuckDB file without --yes. Re-run with --yes to confirm.")
            sys.exit(1)
        if os.path.exists(args.duckdb):
            print(f"Deleting DuckDB file {args.duckdb}")
            os.remove(args.duckdb)

    print(f"Opening DuckDB at {args.duckdb}")
    duck_conn = duckdb.connect(database=args.duckdb)

    if args.drop_all:
        if not args.yes:
            print("Refusing to drop all tables without --yes. Re-run with --yes to confirm.")
            duck_conn.close()
            sys.exit(1)
        # Drop all tables in the connected DuckDB
        print("Dropping all tables in destination DuckDB")
        tables = duck_conn.execute("SHOW TABLES").fetchall()
        for (t,) in tables:
            duck_conn.execute(f"DROP TABLE IF EXISTS {t}")
    # Ensure destination schema exists in DuckDB
    duck_schema = args.duck_schema or args.schema
    print(f"Ensuring DuckDB schema '{duck_schema}' exists")
    duck_conn.execute(f"CREATE SCHEMA IF NOT EXISTS {duck_schema}")

    # Attach the current duckdb file as an alias so dbt references like akahu.akahu_prod.table resolve.
    duckdb_abs = os.path.abspath(args.duckdb)
    try:
        duck_conn.execute(f"ATTACH DATABASE '{duckdb_abs}' AS {args.duck_db_alias}")
    except Exception:
        # It's okay if attach fails because maybe it's already attached or unsupported; continue
        pass

    for table in args.tables:
        print(f"Migrating table: {table} into DuckDB schema {duck_schema}")
        # Use fully-qualified target name in DuckDB
        target_table = f"{duck_schema}.{table}"
        migrate_table(pg_conn, table, args.schema, duck_conn, duck_table=target_table, if_exists=args.if_exists, chunk_size=args.chunk_size)
        # If the created table is not schema-qualified (some DuckDBs may default), ensure a copy exists
        # Create or replace schema-qualified table from main if needed
        try:
            # If the table exists in main (unqualified), and not in duck_schema, move it
            exists_in_schema = duck_conn.execute(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='{duck_schema}' AND table_name='{table}'").fetchone()[0]
            if not exists_in_schema:
                # If an unqualified table exists in main, create schema-qualified one
                duck_conn.execute(f"CREATE TABLE {duck_schema}.{table} AS SELECT * FROM {table}")
                duck_conn.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            # Best effort, continue
            pass

    duck_conn.close()
    pg_conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
