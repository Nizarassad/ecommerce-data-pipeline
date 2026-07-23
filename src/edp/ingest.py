"""Ingest (the E-L in ELT): load raw files into DuckDB under a `raw` schema.

This layer does NOT transform. It faithfully lands the raw files -- dirt and all
-- into `raw.*` tables so the transform layer has a reproducible starting point
and the lineage raw -> staging -> marts is explicit. DuckDB reads CSV and
Parquet natively, so ingest is thin by design.
"""

from __future__ import annotations

import duckdb

from edp.config import Config
from edp.generate import GenerateResult

# raw table name -> (source path key, duckdb reader function)
RAW_TABLES = {
    "raw_customers": ("customers", "read_csv_auto"),
    "raw_products": ("products", "read_csv_auto"),
    "raw_orders": ("orders", "read_parquet"),
    "raw_order_items": ("order_items", "read_parquet"),
    "raw_events": ("events", "read_parquet"),
}


def ingest(gen: GenerateResult, cfg: Config | None = None) -> dict[str, int]:
    """Load every raw file into `raw.<table>` and return landed row counts."""
    cfg = cfg or Config()
    cfg.ensure_dirs()

    con = duckdb.connect(str(cfg.warehouse_path))
    counts: dict[str, int] = {}
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
        for table, (src_key, reader) in RAW_TABLES.items():
            path = gen.paths[src_key]
            con.execute(f"CREATE OR REPLACE TABLE raw.{table} AS "
                        f"SELECT * FROM {reader}('{path}');")
            counts[table] = con.execute(
                f"SELECT count(*) FROM raw.{table}"
            ).fetchone()[0]
    finally:
        con.close()
    return counts


if __name__ == "__main__":  # pragma: no cover
    from edp.generate import generate

    result = ingest(generate())
    for name, c in result.items():
        print(f"{name:18s} {c:>8,} rows")
