"""Transform (the T in ELT): run the layered SQL models in dependency order.

Each `.sql` file under sql/staging and sql/marts builds exactly one model
(`CREATE OR REPLACE TABLE <schema>.<model> AS ...`). Rather than hard-coding an
execution order, we parse each model's dependencies by scanning its SQL for
references to other known models, then topologically sort. This is a tiny,
dependency-free version of what dbt does with `ref()`.

Layer -> schema mapping:
    sql/staging/*.sql  ->  stg.*
    sql/marts/*.sql    ->  marts.*
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

from edp.config import Config

LAYER_SCHEMA = {"staging": "stg", "marts": "marts"}


class ModelDef:
    """A single SQL model: its name, layer, file path and SQL text."""

    def __init__(self, path: Path, layer: str):
        self.path = path
        self.layer = layer
        self.name = path.stem
        self.schema = LAYER_SCHEMA[layer]
        self.sql = path.read_text()

    @property
    def fqn(self) -> str:
        return f"{self.schema}.{self.name}"


def discover_models(sql_dir: Path) -> dict[str, ModelDef]:
    """Load every model file, keyed by model name (unique across layers)."""
    models: dict[str, ModelDef] = {}
    for layer in LAYER_SCHEMA:
        for path in sorted((sql_dir / layer).glob("*.sql")):
            model = ModelDef(path, layer)
            if model.name in models:
                raise ValueError(f"Duplicate model name: {model.name}")
            models[model.name] = model
    return models


def _dependencies(model: ModelDef, all_names: set[str]) -> set[str]:
    """Find which other models this model references in its SQL body.

    A dependency is any OTHER known model name that appears as a whole word in
    the SQL (e.g. `stg.stg_customers` or `marts.fct_orders`). The model's own
    name is excluded so its CREATE target doesn't count as a self-dependency.
    """
    deps: set[str] = set()
    for name in all_names:
        if name == model.name:
            continue
        if re.search(rf"\b{re.escape(name)}\b", model.sql):
            deps.add(name)
    return deps


def topological_order(models: dict[str, ModelDef]) -> list[str]:
    """Return model names in dependency-respecting order (Kahn's algorithm).

    Ties are broken alphabetically for a deterministic, reproducible plan.
    Raises on a dependency cycle.
    """
    names = set(models)
    deps = {n: _dependencies(models[n], names) for n in names}
    resolved: list[str] = []
    remaining = dict(deps)
    while remaining:
        ready = sorted(n for n, d in remaining.items() if d <= set(resolved))
        if not ready:
            raise ValueError(f"Dependency cycle among: {sorted(remaining)}")
        resolved.extend(ready)
        for n in ready:
            remaining.pop(n)
    return resolved


def transform(cfg: Config | None = None) -> dict[str, int]:
    """Build every model in dependency order; return row counts per model."""
    cfg = cfg or Config()
    models = discover_models(cfg.sql_dir)
    order = topological_order(models)

    con = duckdb.connect(str(cfg.warehouse_path))
    counts: dict[str, int] = {}
    try:
        for schema in LAYER_SCHEMA.values():
            con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")
        for name in order:
            model = models[name]
            con.execute(model.sql)
            counts[model.fqn] = con.execute(
                f"SELECT count(*) FROM {model.fqn}"
            ).fetchone()[0]
    finally:
        con.close()
    return counts


def build_plan(cfg: Config | None = None) -> list[str]:
    """Return the fully-qualified model names in execution order (no DB writes)."""
    cfg = cfg or Config()
    models = discover_models(cfg.sql_dir)
    return [models[n].fqn for n in topological_order(models)]


if __name__ == "__main__":  # pragma: no cover
    from edp.generate import generate
    from edp.ingest import ingest

    c = Config()
    ingest(generate(c), c)
    print("Plan:", " -> ".join(build_plan(c)))
    for fqn, n in transform(c).items():
        print(f"{fqn:32s} {n:>8,} rows")
