{{ config(materialized='view') }}

with src as (
    select * from {{ source('akahu_raw', 'account_balances') }}
)
select
  account_id,
  snapshot_date::date as snapshot_date,
  snapshot_at::timestamptz as snapshot_at,
  account_name,
  account_type,
  case
    when lower(coalesce(account_type,'')) like '%credit%' or lower(coalesce(account_type,'')) like '%card%' then true
    else false
  end as is_credit_card,
  connection_name,
  status,
  currency,
  nullif(current::text,'')::numeric as current_balance,
  nullif(available::text,'')::numeric as available_balance,
  nullif("limit"::text,'')::numeric as credit_limit,
  overdrawn::boolean as overdrawn,
  refreshed_balance_at::timestamptz as refreshed_balance_at,
  _dlt_load_id
from src
where account_id is not null and snapshot_date is not null
