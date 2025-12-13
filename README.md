# Akahu Mortgage Dashboard

Personal finance dashboard that uses Akahu data, dbt, DuckDB and Dagster to build a small analytics pipeline and a Flask frontend for visualization.

This repository is intended to be run locally or in Docker for personal use. Remove or redact any sensitive credentials before publishing.

Highlights
- Ingest Akahu data (dlt/Dagster)
- Transform with dbt
- Store models in DuckDB
- Visualize with a Flask + Chart.js dashboard

Dashboard
<img width="2395" height="1293" alt="image" src="https://github.com/user-attachments/assets/0f83438e-d125-43f3-95db-36e986501b47" />

Requirements
- Docker & Docker Compose (recommended for full stack) or local Python 3.10+ to run the dashboard and helper scripts.

Quickstart (Docker - recommended)
1. Copy `.env.example` to `.env` and update any secrets or paths.
2. (Optional) Populate a local DuckDB snapshot for development:

```bash
make install    # creates a venv and installs requirements (optional)
make mockdb     # runs scripts/generate_mock_data.py to create data/akahu.duckdb
```

3. Start the services with Docker Compose:

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

2. Create mock data for development (creates `data/akahu.duckdb`):

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

Run (quick):

```bash
make install
make mockdb
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
- Add a LICENSE file to clarify the project's license. I recommend a permissive license (MIT/Apache-2.0) if you want broad reuse.

Contributing
- See `CONTRIBUTING.md` for basic development instructions. If you want, I can add a GitHub Actions workflow that runs the smoke tests and basic lint checks on PRs.

License
- No license is included by default. Add one if you plan to publish (e.g. `LICENSE` with MIT or Apache-2.0).
