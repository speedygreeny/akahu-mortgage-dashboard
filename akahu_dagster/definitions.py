from dagster import Definitions, load_assets_from_modules, define_asset_job, ScheduleDefinition
from dagster_dbt import DbtCliResource

from .assets import akahu, dbt

akahu_assets = load_assets_from_modules([akahu])
dbt_assets = load_assets_from_modules([dbt])

all_assets_job = define_asset_job(name="materialize_all_assets", selection="*")

# Schedule: run the materialize job daily at 02:00 UTC (adjust cron as needed)
daily_materialize_schedule = ScheduleDefinition(
    job=all_assets_job,
    cron_schedule="0 14 * * *",
    name="daily_materialize_all_assets",
    execution_timezone="UTC",
)

defs = Definitions(
    assets=[*akahu_assets, *dbt_assets],
    resources={
        "dbt": DbtCliResource(project_dir=dbt.dbt_project),
    },
    jobs=[all_assets_job],
    schedules=[daily_materialize_schedule],
)
