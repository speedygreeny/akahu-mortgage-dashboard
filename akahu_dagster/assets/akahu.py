import os
import dlt
import requests
from typing import Iterator, Dict, Any, List
from datetime import datetime, timezone
from dagster import asset, AssetExecutionContext


def _akahu_headers() -> Dict[str, str]:
    """
    Build headers for Akahu Personal Apps auth using env vars.
    Requires AKAHU_USER_TOKEN and AKAHU_APP_TOKEN.
    """
    user_token = os.getenv("AKAHU_USER_TOKEN")
    app_token = os.getenv("AKAHU_APP_TOKEN")
    if not user_token or not app_token:
        raise ValueError("Missing AKAHU_USER_TOKEN or AKAHU_APP_TOKEN in environment.")
    return {
        "Authorization": f"Bearer {user_token}",
        "X-Akahu-Id": app_token,
    }


def _akahu_base_url() -> str:
    return os.getenv("AKAHU_API_URL", "https://api.akahu.io/v1").rstrip("/")


def _get_accounts() -> List[Dict[str, Any]]:
    url = f"{_akahu_base_url()}/accounts"
    headers = _akahu_headers()
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Akahu uses a standard response format; lists are typically under 'items'.
    if isinstance(data, list):
        return data
    return data.get("items") or data.get("result") or []


@dlt.resource(name="accounts", write_disposition="merge", primary_key="_id")
def akahu_accounts() -> Iterator[Dict[str, Any]]:
    """
    Loads Akahu accounts metadata (merged on Akahu account _id).
    """
    for acc in _get_accounts():
        # ensure key presence for merge
        if acc and acc.get("_id"):
            yield acc


@dlt.transformer(
    name="account_balances",
    write_disposition="merge",
    primary_key=("account_id", "snapshot_date"),
)
def akahu_account_balances(account: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """
    Emits a daily balance snapshot per account. Idempotent per (account_id, date).
    """
    if not account:
        return
    account_id = account.get("_id")
    if not account_id:
        return

    bal = account.get("balance") or {}
    # Use UTC date for snapshot key for stability across timezones
    snapshot_dt = datetime.now(timezone.utc)
    snapshot_date = snapshot_dt.date().isoformat()

    yield {
        "account_id": account_id,
        "snapshot_at": snapshot_dt.isoformat(),
        "snapshot_date": snapshot_date,
        "account_name": account.get("name"),
        "account_type": account.get("type"),
        "connection_name": (account.get("connection") or {}).get("name"),
        "status": account.get("status"),
        "currency": bal.get("currency"),
        "current": bal.get("current"),
        "available": bal.get("available"),
        "limit": bal.get("limit"),
        "overdrawn": bal.get("overdrawn"),
        "refreshed_balance_at": (account.get("refreshed") or {}).get("balance"),
        "raw_balance": bal,  # keep raw for auditing/evolution
    }


@dlt.source(name="akahu_finance")
def akahu_source() -> Any:
    """
    Source yielding accounts and a derived account_balances transformer.
    """
    accounts_res = akahu_accounts()
    balances_res = accounts_res | akahu_account_balances
    yield accounts_res
    yield balances_res


@asset(group_name="ingestion", compute_kind="dlt")
def akahu_raw_data(context: AssetExecutionContext):
    """
    Loads Akahu data into DuckDB.
    """
    pipeline = dlt.pipeline(
        pipeline_name="akahu_finance_daily",
        destination=dlt.destinations.duckdb("/data/akahu.duckdb"),
        dataset_name="akahu_prod",
    )

    src = akahu_source()
    load_info = pipeline.run(src)
    context.log.info(load_info)
