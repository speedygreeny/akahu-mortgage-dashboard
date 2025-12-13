# Akahu Mortgage Dashboard

Personal finance dashboard that uses Akahu data, dbt, DuckDB and Dagster to build a small analytics pipeline and a Flask frontend for visualization.

This repository is intended to be run locally or in Docker for personal use. Remove or redact any sensitive credentials before publishing.

Highlights
- Ingest Akahu data (dlt/Dagster)
- Transform with dbt
- Store models in DuckDB
- Visualize with a Flask + Chart.js dashboard

Requirements
- Docker & docker compose (or local Python 3.8+ to run Flask directly)

Quickstart (Docker)
1. Copy `.env.example` to `.env` and update any paths or secrets.
2. Start services:

```bash
docker compose up --build
```

The dashboard will be available at http://localhost:8001/mortgage and Dagster at http://localhost:3000.

Run locally (no Docker)
1. Create a virtualenv and install requirements:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Ensure you have a DuckDB file (see `data/akahu.duckdb` in Docker setups or set `DUCKDB_PATH` in `.env`).

3. Run the Flask app:

```bash
export FLASK_APP=dashboard/app.py
export DUCKDB_PATH=/path/to/akahu.duckdb
flask run --host=0.0.0.0 --port=8001
```

Run with Uvicorn (recommended for local async-friendly runs)
1. Install the requirements (see above).
2. Start with uv (this serves the Flask WSGI app via asgiref -> ASGI):

```bash
# from project root
uvicorn dashboard.asgi:asgi_app --host 0.0.0.0 --port 8001 --workers 1
```

Testing
- A small smoke test is provided in `tests/test_api.py` which expects the service to be running on http://localhost:8001. Run it with:

```bash
pip install pytest requests
pytest -q tests/test_api.py
```

Environment variables
- Use `.env` to provide environment variables. The important ones:
  - `DUCKDB_PATH` - path to the DuckDB file (e.g. `/data/akahu.duckdb` in Docker)
  - `FLASK_ENV`, `FLASK_DEBUG` - optional Flask dev flags

Notes on publishing
- Remove any secrets from the repo (Akahu tokens, local DuckDB snapshots) before publishing.
- Add a license file if you intend to open-source the project.

Contributing
- If you want help wiring CI (Github Actions) to run the smoke tests and linting, I can add a workflow.

License
- No license is included by default. Add one if you plan to publish.
# Akahu Mortgage Dashboard

Personal finance dashboard that uses Akahu data, dbt, DuckDB and Dagster to build a small analytics pipeline and a Flask frontend for visualization.

This repository is intended to be run locally or in Docker for personal use. Remove or redact any sensitive credentials before publishing.

Highlights
- Ingest Akahu data (dlt/Dagster)
- Transform with dbt
- Store models in DuckDB
- Visualize with a Flask + Chart.js dashboard

Requirements
- Docker & docker compose (or local Python 3.8+ to run Flask directly)

Quickstart (Docker)
1. Copy `.env.example` to `.env` and update any paths or secrets.
2. Start services:

```bash
docker compose up --build
```

The dashboard will be available at http://localhost:8001/mortgage and Dagster at http://localhost:3000.

Run locally (no Docker)
1. Create a virtualenv and install requirements:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Ensure you have a DuckDB file (see `data/akahu.duckdb` in Docker setups or set `DUCKDB_PATH` in `.env`).

3. Run the Flask app:

```bash
export FLASK_APP=dashboard/app.py
export DUCKDB_PATH=/path/to/akahu.duckdb
flask run --host=0.0.0.0 --port=8001
```

Run with Uvicorn (recommended for local async-friendly runs)
1. Install the requirements (see above).
2. Start with uv (this serves the Flask WSGI app via asgiref -> ASGI):

```bash
# from project root
uvicorn dashboard.asgi:asgi_app --host 0.0.0.0 --port 8001 --workers 1
```

Testing
- A small smoke test is provided in `tests/test_api.py` which expects the service to be running on http://localhost:8001. Run it with:

```bash
pip install pytest requests
pytest -q tests/test_api.py
```

Environment variables
- Use `.env` to provide environment variables. The important ones:
  - `DUCKDB_PATH` - path to the DuckDB file (e.g. `/data/akahu.duckdb` in Docker)
  - `FLASK_ENV`, `FLASK_DEBUG` - optional Flask dev flags

Notes on publishing
- Remove any secrets from the repo (Akahu tokens, local DuckDB snapshots) before publishing.
- Add a license file if you intend to open-source the project.

Contributing
- If you want help wiring CI (Github Actions) to run the smoke tests and linting, I can add a workflow.

License
- No license is included by default. Add one if you plan to publish.
