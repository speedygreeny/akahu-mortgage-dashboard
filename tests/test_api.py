import requests

BASE = 'http://localhost:8001'


def test_mortgage_over_time_ok():
    r = requests.get(f"{BASE}/api/akahu/mortgage_over_time", timeout=5)
    assert r.status_code == 200
    j = r.json()
    assert isinstance(j, list)
    if len(j) > 0:
        keys = set(j[0].keys())
        assert 'snapshot_date' in keys
        assert 'total_mortgage_balance' in keys


def test_loan_kpis_ok():
    r = requests.get(f"{BASE}/api/akahu/loan_kpis", timeout=5)
    assert r.status_code == 200
    j = r.json()
    assert isinstance(j, dict)
    assert 'total_net_debt' in j
    assert 'monthly_change' in j


def test_accounts_ok():
    r = requests.get(f"{BASE}/api/akahu/accounts", timeout=5)
    assert r.status_code == 200
    j = r.json()
    assert isinstance(j, list)
    if len(j) > 0:
        keys = set(j[0].keys())
        assert 'account_id' in keys
        assert 'is_credit_card' in keys
