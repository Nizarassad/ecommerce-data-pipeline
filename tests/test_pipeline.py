"""End-to-end pipeline orchestration (topological backend)."""

from __future__ import annotations

from edp.config import Config
from edp.pipeline import _toposort, run_pipeline


def test_toposort_respects_dependencies():
    dag = {"a": set(), "b": {"a"}, "c": {"a", "b"}, "d": {"c"}}
    order = _toposort(dag)
    assert order.index("a") < order.index("b") < order.index("c") < order.index("d")


def test_toposort_detects_cycle():
    dag = {"a": {"b"}, "b": {"a"}}
    try:
        _toposort(dag)
    except ValueError as e:
        assert "Cycle" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected a cycle error")


def test_run_pipeline_topological(tmp_path):
    cfg = Config(raw_dir=tmp_path / "raw", warehouse_path=tmp_path / "wh.duckdb")
    result = run_pipeline(cfg, prefer_prefect=False)

    assert result.orchestrator == "topological"
    assert result.quality_passed
    assert result.ingest_counts["raw_orders"] == 5000
    assert result.transform_counts["marts.fct_orders"] == 5000
    # Plan is dependency-ordered and complete.
    assert result.plan[0].startswith("stg.")
    assert result.plan[-1].startswith("marts.")
    assert result.duration_s > 0
