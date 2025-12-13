{{ config(materialized='table') }}

with daily as (
  select * from {{ ref('fct_account_daily_balances') }}
)
select
  snapshot_date,
  sum(case when upper(coalesce(account_type,'')) = 'LOAN' and coalesce(is_credit_card,false) = false then coalesce(current_balance,0) else 0 end) as total_mortgage_balance,
  sum(case when coalesce(is_credit_card,false) = true then coalesce(current_balance,0) else 0 end) as total_creditcard_balance,
  sum(coalesce(current_balance,0)) as total_net_debt,
  sum(case when upper(coalesce(account_type,'')) = 'LOAN' and coalesce(is_credit_card,false) = false then coalesce(available_balance,0) else 0 end) as total_available,
  sum(case when upper(coalesce(account_type,'')) = 'LOAN' and coalesce(is_credit_card,false) = false then coalesce(credit_limit,0) else 0 end) as total_limit
from daily
group by snapshot_date
order by snapshot_date
