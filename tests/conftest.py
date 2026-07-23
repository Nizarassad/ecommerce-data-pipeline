"""Shared fixtures: build a throwaway warehouse in a temp dir once per session.

Tests use the topological runner (prefer_prefect=False) so they are fast,
deterministic and never depend on Prefect being installed.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from edp.config import Config
from edp.pipeline import run_pipeline


@pytest.fixture(scope="session")
def cfg(tmp_path_factory: pytest.TempPathFactory) -> Config:
    root = tmp_path_factory.mktemp("edp")
    return Config(
        raw_dir=root / "raw",
        warehouse_path=root / "warehouse.duckdb",
        # sql_dir points at the real repo SQL (two levels up from tests/).
        sql_dir=Path(__file__).resolve().parents[1] / "sql",
    )


@pytest.fixture(scope="session")
def built(cfg: Config):
    """Run the full pipeline once (topological backend) and return the result."""
    return run_pipeline(cfg, prefer_prefect=False)


@pytest.fixture()
def con(cfg: Config, built):
    c = duckdb.connect(str(cfg.warehouse_path), read_only=True)
    yield c
    c.close()
