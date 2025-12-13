{{ config(materialized='view') }}

with acc as (
  select * from {{ ref('stg_akahu_accounts') }}
), latest as (
  -- If multiple records exist per account (schema evolution), pick the most recently refreshed
  select *,
    row_number() over (partition by account_id order by _dlt_load_id desc) as rn
  from acc
)
select
  account_id,
  account_name,
  account_type,
  status,
  loan_interest_rate,
  loan_interest_type,
  loan_interest_expires_at,
  is_interest_only,
  term_years,
  term_months,
  loan_matures_at,
  loan_initial_principal,
  repayment_frequency,
  repayment_next_date,
  repayment_next_amount
from latest
where rn = 1
  and upper(coalesce(account_type,'')) = 'LOAN'
  and coalesce(is_credit_card, false) = false
