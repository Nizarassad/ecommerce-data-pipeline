"""edp - E-commerce ELT Data Pipeline.

A small but production-shaped ELT pipeline that runs entirely offline:

    generate -> ingest (EL) -> transform (T, layered SQL) -> quality tests

The "warehouse" is an embedded DuckDB database. Transforms are plain SQL,
organised in dbt-style layers (raw -> staging -> marts). Data-quality tests
are implemented in-repo (not a dependency) and run against the built warehouse.
"""

from edp.config import Config

__all__ = ["Config"]
__version__ = "0.1.0"
