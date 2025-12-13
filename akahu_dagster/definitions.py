from dagster import Definitions, load_assets_from_modules, define_asset_job
from dagster_dbt import DbtCliResource

from .assets import akahu, dbt

akahu_assets = load_assets_from_modules([akahu])
dbt_assets = load_assets_from_modules([dbt])

all_assets_job = define_asset_job(name="materialize_all_assets", selection="*")

defs = Definitions(
    assets=[*akahu_assets, *dbt_assets],
    resources={
        "dbt": DbtCliResource(project_dir=dbt.dbt_project),
    },
    jobs=[all_assets_job],
)
