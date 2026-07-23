"""CLI: run the whole pipeline and print a REAL summary.

    python -m edp.run            # or:  edp

Prints landed row counts per raw table, built row counts per model, the
data-quality report, and a couple of headline analytics numbers pulled live
from the warehouse (total revenue, top products). Every number is queried from
the warehouse that was just built -- nothing is hard-coded.
"""

from __future__ import annotations

import argparse
import logging
import sys

import duckdb

from edp.config import Config
from edp.pipeline import PipelineResult, run_pipeline


def _analytics(cfg: Config) -> dict:
    """Pull a few headline numbers straight from the built marts."""
    con = duckdb.connect(str(cfg.warehouse_path), read_only=True)
    try:
        total_revenue = con.execute(
            "SELECT SUM(net_revenue) FROM marts.fct_orders"
        ).fetchone()[0]
        valid_orders = con.execute(
            "SELECT COUNT(*) FROM marts.fct_orders WHERE is_valid_sale"
        ).fetchone()[0]
        aov = con.execute(
            "SELECT SUM(net_revenue) / NULLIF(COUNT(*) FILTER (WHERE is_valid_sale), 0) "
            "FROM marts.fct_orders"
        ).fetchone()[0]
        top_products = con.execute(
            """
            SELECT p.product_name, p.category,
                   SUM(oi.line_revenue) AS revenue
            FROM stg.stg_order_items oi
            JOIN marts.dim_products p USING (product_id)
            JOIN marts.fct_orders o USING (order_id)
            WHERE o.is_valid_sale
            GROUP BY p.product_name, p.category
            ORDER BY revenue DESC
            LIMIT 5
            """
        ).fetchall()
        top_customers = con.execute(
            """
            SELECT customer_id, segment, lifetime_revenue
            FROM marts.customer_lifetime_value
            ORDER BY lifetime_revenue DESC
            LIMIT 3
            """
        ).fetchall()
        rev_by_channel = con.execute(
            """
            SELECT channel, SUM(net_revenue) AS revenue
            FROM marts.fct_orders
            GROUP BY channel ORDER BY revenue DESC
            """
        ).fetchall()
    finally:
        con.close()
    return {
        "total_revenue": total_revenue,
        "valid_orders": valid_orders,
        "aov": aov,
        "top_products": top_products,
        "top_customers": top_customers,
        "rev_by_channel": rev_by_channel,
    }


def _print_summary(result: PipelineResult, cfg: Config) -> None:
    line = "=" * 66
    print(line)
    print("  E-COMMERCE ELT PIPELINE  -  RUN SUMMARY")
    print(line)
    print(f"  orchestrator : {result.orchestrator}")
    print(f"  duration     : {result.duration_s:.2f}s")

    print("\n  RAW (ingested) -----------------------------------------------")
    for name, n in result.ingest_counts.items():
        print(f"    {name:<22s} {n:>8,} rows")

    print("\n  MODELS (built, in dependency order) --------------------------")
    for fqn in result.plan:
        n = result.transform_counts.get(fqn, 0)
        print(f"    {fqn:<34s} {n:>8,} rows")

    print("\n  DATA QUALITY -------------------------------------------------")
    if result.quality is not None:
        print(result.quality.as_table())
        verdict = "ALL CHECKS PASSED" if result.quality.passed else "QUALITY FAILURES"
        print(f"\n    -> {result.quality.n_passed} passed, "
              f"{result.quality.n_failed} failed  [{verdict}]")

    a = _analytics(cfg)
    print("\n  ANALYTICS (live from warehouse) ------------------------------")
    print(f"    total net revenue : {a['total_revenue']:,.2f}")
    print(f"    valid orders      : {a['valid_orders']:,}")
    print(f"    avg order value   : {a['aov']:,.2f}")
    print("    top 5 products by revenue:")
    for name, cat, rev in a["top_products"]:
        print(f"      - {name:<10s} {cat:<12s} {rev:>12,.2f}")
    print("    revenue by channel:")
    for ch, rev in a["rev_by_channel"]:
        print(f"      - {ch:<12s} {rev:>12,.2f}")
    print(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edp", description="Run the e-commerce ELT pipeline.")
    parser.add_argument(
        "--no-prefect", action="store_true",
        help="Force the topological runner even if Prefect is installed.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress task-level logs.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = Config()
    result = run_pipeline(cfg, prefer_prefect=not args.no_prefect)
    _print_summary(result, cfg)
    return 0 if result.quality_passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
