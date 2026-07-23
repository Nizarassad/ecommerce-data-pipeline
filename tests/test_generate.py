"""Generator determinism and shape."""

from __future__ import annotations

import pandas as pd

from edp.config import Config
from edp.generate import generate


def _make(tmp_path, seed=42) -> Config:
    return Config(
        seed=seed,
        raw_dir=tmp_path / "raw",
        warehouse_path=tmp_path / "wh.duckdb",
    )


def test_generate_is_deterministic(tmp_path):
    """Same seed -> byte-identical customer feed across two runs."""
    a = generate(_make(tmp_path / "a"))
    b = generate(_make(tmp_path / "b"))

    assert a.counts == b.counts
    df_a = pd.read_csv(a.paths["customers"])
    df_b = pd.read_csv(b.paths["customers"])
    pd.testing.assert_frame_equal(df_a, df_b)


def test_generate_volumes(tmp_path):
    res = generate(_make(tmp_path))
    # 1000 base customers + injected duplicates (n // 50 = 20).
    assert res.counts["customers"] == 1020
    assert res.counts["products"] == 200
    assert res.counts["orders"] == 5000
    # Line items and events are variable but bounded and larger than orders.
    assert res.counts["order_items"] > res.counts["orders"]
    assert res.counts["events"] > res.counts["orders"]


def test_generate_injects_dirt(tmp_path):
    """Raw customers must contain the dirt staging is expected to clean."""
    res = generate(_make(tmp_path))
    df = pd.read_csv(res.paths["customers"], dtype=str)
    # Some emails carry stray whitespace...
    assert (df["email"] != df["email"].str.strip()).any()
    # ...and there are exact-duplicate customer_ids (dedup target downstream).
    assert df["customer_id"].duplicated().any()


def test_different_seed_changes_data(tmp_path):
    a = generate(_make(tmp_path / "a", seed=1))
    b = generate(_make(tmp_path / "b", seed=2))
    df_a = pd.read_csv(a.paths["orders"] if False else a.paths["customers"])
    df_b = pd.read_csv(b.paths["customers"])
    assert not df_a.equals(df_b)
