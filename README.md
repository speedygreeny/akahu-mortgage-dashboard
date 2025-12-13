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
# Akahu Mortgage Dashboard

This project provides a personal finance dashboard for tracking mortgage and loan accounts using Akahu data.
It uses a modern local data stack:
- **Ingestion**: [dlt](https://dlthub.com/) (Data Load Tool) to pull data from Akahu API.
- **Transformation**: [dbt](https://www.getdbt.com/) (Data Build Tool) to model the data.
- **Orchestration**: [Dagster](https://dagster.io/) to schedule and manage the pipeline.
- **Storage**: [DuckDB](https://duckdb.org/) as the analytical database.
- **Visualization**: A custom Flask web application.

## Setup

1.  **Prerequisites**: Docker and Docker Compose.
2.  **Environment Variables**: Create a `.env` file in the root directory with your Akahu credentials:
    ```bash
    AKAHU_USER_TOKEN=your_user_token
    AKAHU_APP_TOKEN=your_app_token
    ```
3.  **Run**:
    ```bash
    docker-compose up --build
    ```

## Access

- **Dagster UI**: [http://localhost:3000](http://localhost:3000)
    - Go here to materialize assets (run the pipeline).
    - Click "Materialize All" to load data and run dbt models.
- **Dashboard**: [http://localhost:8001/mortgage](http://localhost:5001/mortgage)
    - View your mortgage stats.

## Project Structure

- `akahu_dagster/`: Dagster assets and definitions.
- `dbt_project/`: dbt models for transforming raw Akahu data.
- `dashboard/`: Flask application for the frontend.
