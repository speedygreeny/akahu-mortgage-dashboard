from pathlib import Path

from dagster import AssetExecutionContext
from dagster_dbt import DbtCliResource, dbt_assets, DbtProject, DagsterDbtTranslator
from dagster import AssetKey

DBT_PROJECT_DIR = Path(__file__).joinpath("..", "..", "..", "dbt_project").resolve()
dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR)
dbt_project.prepare_if_dev()

# Avoid validating/reading the dbt manifest at import time because the manifest
# may not exist until `dbt compile`/`dbt build` has been run. If we attempt to
# call the `@dbt_assets` decorator with a missing manifest the decorator will
# try to resolve and read the manifest and raise an error during module import
# which prevents Dagster from loading the package.
manifest_path = dbt_project.manifest_path
manifest_path = dbt_project.manifest_path

# If a dbt manifest exists, use dagster_dbt to generate native dbt-backed assets.
if manifest_path.exists():
    from dagster import AssetExecutionContext, AssetKey

    # Build a mapping from dbt manifest sources to the single DLT asset
    # `akahu_raw_data` so Dagster knows the dbt models that read those
    # sources depend on the DLT asset. Manifest source node keys look like:
    # 'source.<package>.<source_name>.<table>'. We'll map every source table to
    # the same AssetKey(['akahu_raw_data']).
    # Create a translator that maps dbt `source` resources to the single
    # ingestion asset `akahu_raw_data`. This tells dagster_dbt that any dbt
    # source (regardless of package/name/table) should be represented by that
    # asset key in the Dagster asset graph.
    class _AkahuTranslator(DagsterDbtTranslator):
        def get_asset_key(self, dbt_resource_props):
            # Give each dbt source a unique asset key under the `akahu_raw` prefix.
            # This satisfies Dagster's uniqueness requirement while keeping the
            # assets clearly associated with the raw ingestion data.
            if dbt_resource_props and dbt_resource_props.get("resource_type") == "source":
                # keep values for potential debugging but avoid unused-variable lint errors
                _pkg = dbt_resource_props.get("package_name") or dbt_resource_props.get("package")
                _source_name = dbt_resource_props.get("source_name")
                name = dbt_resource_props.get("name")
                # Example AssetKey: ["akahu_raw", "accounts"]
                return AssetKey(["akahu_raw", name])

            return super().get_asset_key(dbt_resource_props)

    translator = _AkahuTranslator()

    # Create lightweight Dagster source assets that are produced by the
    # `akahu_raw_data` ingestion asset. We derive these from the manifest so
    # that dbt model assets which depend on those sources will see proper
    # upstream dependencies in the Dagster asset graph.
    source_assets = []
    try:
        import json
        manifest = json.loads(manifest_path.read_text())
    except Exception:
        manifest = {}

    for unique_id, node in manifest.get("sources", {}).items():
        props = node.get("metadata", {}) if isinstance(node, dict) else {}
        # dbt source node has a 'name' and belongs to a 'source_name'/'table'
        name = node.get("name") if isinstance(node, dict) else None
        if not name:
            continue

        asset_key = AssetKey(["akahu_raw", name])

        # Create a trivial asset that declares it depends on the single
        # ingestion asset `akahu_raw_data`. The op body is a no-op; the real
        # data comes from the DuckDB file written by the DLT pipeline.
        from dagster import asset, AssetIn

        # Use key_prefix so the resulting AssetKey matches the translator's
        # output: AssetKey(["akahu_raw", name])
        @asset(name=name, key_prefix=["akahu_raw"], ins={"akahu_raw_data": AssetIn("akahu_raw_data")})
        def _src_asset(akahu_raw_data):
            # This asset acts as a logical pointer to the table produced by
            # the ingestion step. It doesn't need to read data here; it's a
            # graph-level dependency.
            return None

    source_assets.append((name, _src_asset))

    @dbt_assets(manifest=manifest_path, dagster_dbt_translator=translator)
    def dbt_models(context: AssetExecutionContext, dbt: DbtCliResource):
        # Stream the dbt build output (this runs models in dependency order).
        yield from dbt.cli(["build"], context=context).stream()

    # Export both the dbt-generated assets and the synthetic source assets so
    # Dagster discovers them together when this module is imported.
    dbt_generated_assets = dbt_models
    # If any source assets were created above, expose them in the module
    # globals so the definitions loader picks them up.
    for name, a in source_assets:
        # Module-level variable names must be valid identifiers. Prefix with
        # akahu_raw_ to avoid collisions.
        var_name = f"akahu_raw_{name}"
        globals()[var_name] = a
else:
    # No manifest yet — fallback to previous behavior: define a no-op placeholder
    def dbt_models(*args, **kwargs):
        return
