"""Transform layer: dependency ordering, dedup, and expected schema."""

from __future__ import annotations

from edp.config import Config
from edp.transform import build_plan, discover_models, topological_order


def test_plan_orders_staging_before_marts(cfg: Config):
    plan = build_plan(cfg)
    # Staging models must all appear before any mart that depends on them.
    assert plan.index("stg.stg_customers") < plan.index("marts.dim_customers")
    assert plan.index("marts.dim_customers") < plan.index("marts.fct_orders")
    # The analytics marts depend on fct_orders, so they come last.
    assert plan.index("marts.fct_orders") < plan.index("marts.customer_lifetime_value")
    assert plan.index("marts.fct_orders") < plan.index("marts.daily_revenue")


def test_dependencies_detected(cfg: Config):
    models = discover_models(cfg.sql_dir)
    order = topological_order(models)
    # customer_lifetime_value references dim_customers and fct_orders.
    assert "dim_customers" in order and "fct_orders" in order
    assert order.index("fct_orders") < order.index("customer_lifetime_value")


def test_staging_dedupes_customers(con):
    """1020 raw customers (with 20 injected dups) -> 1000 unique in staging."""
    raw = con.execute("SELECT count(*) FROM raw.raw_customers").fetchone()[0]
    stg = con.execute("SELECT count(*) FROM stg.stg_customers").fetchone()[0]
    distinct = con.execute(
        "SELECT count(DISTINCT customer_id) FROM stg.stg_customers"
    ).fetchone()[0]
    assert raw == 1020
    assert stg == 1000 == distinct


def test_fct_orders_expected_columns(con):
    cols = {r[1] for r in con.execute("PRAGMA table_info('marts.fct_orders')").fetchall()}
    expected = {
        "order_id", "customer_id", "order_ts", "order_date", "status",
        "channel", "is_valid_sale", "item_count", "units",
        "gross_revenue", "net_revenue",
    }
    assert expected <= cols


def test_staging_cleans_emails(con):
    """No staged email has surrounding whitespace or uppercase letters."""
    bad = con.execute(
        "SELECT count(*) FROM stg.stg_customers "
        "WHERE email <> lower(trim(email))"
    ).fetchone()[0]
    assert bad == 0


def test_net_revenue_zero_for_invalid_sales(con):
    bad = con.execute(
        "SELECT count(*) FROM marts.fct_orders "
        "WHERE NOT is_valid_sale AND net_revenue <> 0"
    ).fetchone()[0]
    assert bad == 0
