# Architecture overview

This project is split into a few main components:

- Data ingestion & orchestration: Dagster (`akahu_dagster/`) runs assets to fetch and store Akahu data.
- Transformations: dbt models in `dbt_project/` transform raw Akahu data into analytics-friendly tables stored in DuckDB.
- Storage: DuckDB database stored at `data/akahu.duckdb` (or any path set by `DUCKDB_PATH`).
- Visualization: Flask app in `dashboard/` provides a simple UI and JSON endpoints backed by DuckDB.

Typical data flow:

1. Dagster / dlt fetches raw Akahu records and writes to `akahu_prod` schema in DuckDB.
2. dbt transforms staging tables into analytical models (fct_*, dim_*), stored in the same DuckDB.
3. The Flask dashboard queries the transformed tables (`fct_mortgage_over_time`, `fct_account_daily_balances`, etc.) to power the UI.

For local development, `scripts/generate_mock_data.py` creates a synthetic `akahu_prod` schema and `scripts/create_minimal_views.py` provides minimal dbt-like views so the dashboard can be used without running dbt.
