"""Ingest lands every raw file with matching row counts."""

from __future__ import annotations

from edp.config import Config
from edp.generate import generate
from edp.ingest import RAW_TABLES, ingest


def test_ingest_row_counts_match_source(tmp_path):
    cfg = Config(raw_dir=tmp_path / "raw", warehouse_path=tmp_path / "wh.duckdb")
    gen = generate(cfg)
    landed = ingest(gen, cfg)

    # Every configured raw table was created.
    assert set(landed) == set(RAW_TABLES)
    # Landed counts equal the generated counts (ingest transforms nothing).
    assert landed["raw_customers"] == gen.counts["customers"] == 1020
    assert landed["raw_orders"] == gen.counts["orders"] == 5000
    assert landed["raw_order_items"] == gen.counts["order_items"]
    assert landed["raw_events"] == gen.counts["events"]
