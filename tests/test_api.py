import os
import subprocess
import sys
import pytest

from dashboard.app import app as flask_app


def ensure_mock_db():
    """Create a mock DB if one doesn't exist. This is safe and fast for CI runs."""
    repo_root = os.path.dirname(os.path.dirname(__file__))
    duckdb_path = os.path.join(repo_root, "data", "akahu.duckdb")
    if os.path.exists(duckdb_path):
        return duckdb_path

    # Try to run the generate script. If it fails, re-raise so CI shows the error.
    gen_script = os.path.join(repo_root, "scripts", "generate_mock_data.py")
    views_script = os.path.join(repo_root, "scripts", "create_minimal_views.py")
    python = sys.executable or "python3"
    subprocess.check_call([python, gen_script])
    # create minimal views used by dbt / frontend
    subprocess.check_call([python, views_script])
    return duckdb_path


@pytest.fixture(scope="session")
def client():
    # Ensure DB exists so endpoints don't 500
    repo_root = os.path.dirname(os.path.dirname(__file__))
    duckdb_path = os.path.join(repo_root, "data", "akahu.duckdb")
    if not os.path.exists(duckdb_path):
        ensure_mock_db()

    # Ensure the app uses the repo-local DB by default in tests
    os.environ.setdefault("DUCKDB_PATH", duckdb_path)

    flask_app.testing = True
    with flask_app.test_client() as c:
        yield c


def test_mortgage_over_time_ok(client):
    r = client.get("/api/akahu/mortgage_over_time")
    assert r.status_code == 200
    j = r.get_json()
    assert isinstance(j, list)
    if len(j) > 0:
        keys = set(j[0].keys())
        assert 'snapshot_date' in keys
        assert 'total_mortgage_balance' in keys


def test_loan_kpis_ok(client):
    r = client.get("/api/akahu/loan_kpis")
    assert r.status_code == 200
    j = r.get_json()
    assert isinstance(j, dict)
    assert 'total_net_debt' in j
    assert 'monthly_change' in j


def test_accounts_ok(client):
    r = client.get("/api/akahu/accounts")
    assert r.status_code == 200
    j = r.get_json()
    assert isinstance(j, list)
    if len(j) > 0:
        keys = set(j[0].keys())
        assert 'account_id' in keys
        assert 'is_credit_card' in keys
