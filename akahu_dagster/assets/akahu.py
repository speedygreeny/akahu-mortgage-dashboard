import os
import dlt
import requests
import logging
from typing import Iterator, Dict, Any, List
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
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
    # materialize accounts to allow logging of counts and refreshed timestamps
    accounts = _get_accounts()
    try:
        accounts = list(accounts)
    except TypeError:
        # if _get_accounts already returned a list, this will still work
        pass

    # compute simple metrics for logging
    count = len(accounts) if hasattr(accounts, "__len__") else sum(1 for _ in accounts)
    refreshed_vals = [
        (a.get("refreshed") or {}).get("balance") for a in accounts if a
    ]
    latest_refreshed = None
    parsed_dates: List[datetime] = []
    for v in refreshed_vals:
        if not v:
            continue
        try:
            parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
            parsed_dates.append(parsed)
        except Exception:
            # keep original string if parsing fails
            continue
    if parsed_dates:
        latest_refreshed = max(parsed_dates).isoformat()
    else:
        # fall back to raw string if any
        latest_refreshed = max((v for v in refreshed_vals if v), default=None)

    logger = logging.getLogger(__name__)
    logger.info("Akahu accounts fetched: %d", count)
    logger.info("Latest account 'refreshed.balance' timestamp: %s", latest_refreshed)

    for acc in accounts:
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
    # Use UTC for `snapshot_at` (stable canonical timestamp) but derive the
    # human-readable `snapshot_date` in the user's local timezone (NZ) so the
    # dashboard shows the expected local date.
    snapshot_dt_utc = datetime.now(timezone.utc)
    try:
        nz_tz = ZoneInfo("Pacific/Auckland")
        snapshot_dt_local = snapshot_dt_utc.astimezone(nz_tz)
    except Exception:
        # If zoneinfo isn't available for some reason, fall back to UTC date
        snapshot_dt_local = snapshot_dt_utc

    snapshot_date = snapshot_dt_local.date().isoformat()

    # Log the snapshot timestamps (UTC and NZ local date) once to avoid noisy per-account logs
    if not hasattr(akahu_account_balances, "_snapshot_logged"):
        logger = logging.getLogger(__name__)
        logger.info("Creating Akahu account balance snapshot: snapshot_at(UTC)=%s, snapshot_date(NZ)=%s", snapshot_dt_utc.isoformat(), snapshot_date)
        setattr(akahu_account_balances, "_snapshot_logged", True)

    yield {
        "account_id": account_id,
        "snapshot_at": snapshot_dt_utc.isoformat(),
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

    # Log the raw load_info to Dagster logs for visibility and also a concise summary
    context.log.info("DLT pipeline run result: %s", load_info)
    logger = logging.getLogger(__name__)
    logger.info("DLT pipeline run completed. run_info: %s", load_info)
