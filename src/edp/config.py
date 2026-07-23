"""Central configuration for the pipeline.

Everything is path- and volume-based so the whole run is reproducible and
self-contained inside the repository. No environment variables are required.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

# Repo root = two levels up from this file (src/edp/config.py -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]


class Config(BaseModel):
    """Runtime configuration.

    Volumes are intentionally modest so the pipeline runs in a few seconds on a
    laptop while still exercising joins, dedup, and aggregation at a realistic
    shape.
    """

    seed: int = 42

    # Synthetic data volumes.
    n_customers: int = 1_000
    n_products: int = 200
    n_orders: int = 5_000
    # Events are generated per order (browse/add-to-cart/purchase funnel), so
    # the events table ends up several times larger than orders.

    # Filesystem layout.
    root: Path = Field(default=REPO_ROOT)
    raw_dir: Path = Field(default=REPO_ROOT / "data" / "raw")
    warehouse_path: Path = Field(default=REPO_ROOT / "data" / "warehouse.duckdb")
    sql_dir: Path = Field(default=REPO_ROOT / "sql")

    # Freshness check: max age (days) of the most recent order relative to the
    # generator's "today". Synthetic data is anchored to a fixed reference date.
    freshness_max_age_days: int = 2

    model_config = {"arbitrary_types_allowed": True}

    def ensure_dirs(self) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.warehouse_path.parent.mkdir(parents=True, exist_ok=True)
