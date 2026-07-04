{{ config(materialized='table') }}

{% set excluded = var('excluded_connections', []) | map('lower') | list %}

-- If multiple loads happen within the same day, take the latest snapshot for that day/account to avoid double counting.
with balances as (
  select * from {{ ref('stg_akahu_account_balances') }}
  {% if excluded %}
  where lower(coalesce(connection_name,'')) not in ({{ "'" ~ excluded | join("','") ~ "'" }})
  {% endif %}
), ranked as (
  select
    account_id,
    snapshot_date,
    account_name,
    account_type,
    is_credit_card,
    connection_name,
    status,
    currency,
    current_balance,
    available_balance,
    credit_limit,
    refreshed_balance_at,
    snapshot_at,
    _dlt_load_id,
    row_number() over (
      partition by account_id, snapshot_date
      order by _dlt_load_id desc, snapshot_at desc nulls last
    ) as rn
  from balances
)
select
  account_id,
  snapshot_date,
  account_name,
  account_type,
  is_credit_card,
  connection_name,
  status,
  currency,
  current_balance,
  available_balance,
  credit_limit,
  refreshed_balance_at,
  snapshot_at as last_snapshot_at,
  _dlt_load_id
from ranked
where rn = 1
