# Akahu Mortgage Dashboard

Personal finance dashboard that uses Akahu data, dbt, DuckDB and Dagster to build a small analytics pipeline and a Flask frontend for visualization.

This repository is intended to be run locally or in Docker for personal use. Be sure to remove or redact any sensitive credentials before publishing.

Highlights
- Ingest Akahu data (dlt/Dagster)
- Transform with dbt
- Store models in DuckDB
- Visualize with a Flask + Chart.js dashboard

Dashboard
<img width="2395" height="1293" alt="image" src="https://github.com/user-attachments/assets/0f83438e-d125-43f3-95db-36e986501b47" />

Requirements
- Docker & Docker Compose (recommended for full stack) or local Python 3.10+ to run the dashboard and helper scripts.

Quickstart

1. Register an Akahu application and obtain credentials

   - Create an Akahu developer app and copy the credentials. You will need:
     - `AKAHU_USER_TOKEN`
     - `AKAHU_APP_TOKEN`

2. Copy the example env and update secrets

```bash
cp .env.example .env
# Edit .env and set AKAHU_USER_TOKEN and AKAHU_APP_TOKEN (and any paths like DUCKDB_PATH)
```

3. Install project dependencies

```bash
make install
```

Note: Creating a local mock DuckDB snapshot is optional for development. If you want example data, run:

```bash
make mockdb     # optional: creates data/akahu.duckdb with synthetic data
```

Docker (recommended for full stack)

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

2. (Optional) Create mock data for development (creates `data/akahu.duckdb`):

```bash
python3 scripts/generate_mock_data.py
python3 scripts/create_minimal_views.py
```

3. Run the Flask app directly (for quick local dev):

```bash
export DUCKDB_PATH=./data/akahu.duckdb
python dashboard/app.py
```

Optional: run via ASGI with Uvicorn (serves the same Flask app via ASGI wrapper):

```bash
uvicorn dashboard.asgi:asgi_app --host 0.0.0.0 --port 8001 --workers 1
```

Testing
- A small smoke test is provided in `tests/test_api.py` which expects the service to be running on http://localhost:8001.

Run tests (example):

```bash
make install
# optionally create mock DB first: make mockdb
python3 scripts/create_minimal_views.py
pytest -q tests/test_api.py
```

Environment variables
- Use `.env` to provide environment variables (or set them in your shell). Important ones:
  - `DUCKDB_PATH` - path to the DuckDB file (e.g. `/data/akahu.duckdb` in Docker)
  - `AKAHU_USER_TOKEN`, `AKAHU_APP_TOKEN` - Akahu credentials (redact before publishing)
  - `FLASK_ENV`, `FLASK_DEBUG` - optional Flask dev flags

Notes on publishing
- Remove any secrets from the repo (Akahu tokens, local DuckDB snapshots) before publishing.

Contributing
- See `CONTRIBUTING.md` for basic development instructions.

License
- Add a LICENSE file if you plan to publish (e.g. `LICENSE` with MIT or Apache-2.0).
