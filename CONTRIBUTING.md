# Contributing

Thanks for your interest in contributing! A few small notes to make contributing easier:

- Please open issues for feature requests or bugs before sending a PR.
- Keep changes small and atomic; update README where run instructions change.
- Add tests for new behavior where practical (this repo includes a small smoke test in `tests/test_api.py`).
- Use the existing code style (Python 3.10+). Run tests with `pytest`.

Local dev quick commands (from project root):

```bash
# Create venv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Generate mock data (creates data/akahu.duckdb)
python3 scripts/generate_mock_data.py

# Run dashboard
export DUCKDB_PATH=./data/akahu.duckdb
python dashboard/app.py
```

If you'd like a CI workflow added (GitHub Actions) to run tests and linting, open an issue or PR and I can add a suggested workflow.
