{{ config(materialized='view') }}

with src as (
    select * from {{ source('akahu_raw', 'transactions') }}
)
select
  _id as transaction_id,
  _account as account_id,
  _connection as connection_id,
  nullif("date"::text,'')::timestamptz as txn_at,
  nullif("date"::text,'')::date as txn_date,
  description,
  nullif(amount::text,'')::numeric as amount,
  nullif(balance::text,'')::numeric as balance,
  type as txn_type,
  nullif(created_at::text,'')::timestamptz as created_at,
  _dlt_load_id
from src
where _id is not null
