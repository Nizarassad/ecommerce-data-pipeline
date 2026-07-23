"""Quality suite: passes on clean data, and each check bites on bad data."""

from __future__ import annotations

import duckdb

from edp.config import Config
from edp.quality import (
    AcceptedValues,
    NotNull,
    RelationshipsTest,
    Unique,
    build_suite,
    run_quality,
)


def test_full_suite_passes_on_clean_warehouse(cfg: Config, built):
    report = run_quality(cfg)
    assert report.passed, report.as_table()
    assert report.n_failed == 0
    # Sanity: the suite is non-trivial.
    assert len(report.results) >= 15


def test_referential_integrity_holds(cfg: Config, built):
    con = duckdb.connect(str(cfg.warehouse_path), read_only=True)
    try:
        check = RelationshipsTest(
            "marts.fct_orders", "customer_id", "marts.dim_customers", "customer_id"
        )
        result = check.run(con)
    finally:
        con.close()
    assert result.passed
    assert result.failing_rows == 0


def test_orphan_order_is_caught(cfg: Config, built, tmp_path):
    """Inject an orphan order (customer_id with no matching customer) into a
    COPY of the warehouse and prove the relationships check fails on it."""
    import shutil

    corrupt = tmp_path / "corrupt.duckdb"
    shutil.copy(cfg.warehouse_path, corrupt)

    con = duckdb.connect(str(corrupt))
    try:
        # 999999 does not exist in dim_customers.
        con.execute(
            "INSERT INTO marts.fct_orders "
            "(order_id, customer_id, order_ts, order_date, status, channel, "
            " is_valid_sale, item_count, units, gross_revenue, net_revenue) "
            "VALUES (999999, 999999, now(), current_date, 'completed', 'web', "
            " true, 1, 1, 10.0, 10.0)"
        )
        check = RelationshipsTest(
            "marts.fct_orders", "customer_id", "marts.dim_customers", "customer_id"
        )
        result = check.run(con)
    finally:
        con.close()

    assert not result.passed
    assert result.failing_rows == 1


def test_unique_check_catches_duplicate(cfg: Config, built, tmp_path):
    import shutil

    corrupt = tmp_path / "dup.duckdb"
    shutil.copy(cfg.warehouse_path, corrupt)
    con = duckdb.connect(str(corrupt))
    try:
        con.execute(
            "INSERT INTO marts.dim_customers SELECT * FROM marts.dim_customers LIMIT 1"
        )
        result = Unique("marts.dim_customers", "customer_id").run(con)
    finally:
        con.close()
    assert not result.passed
    assert result.failing_rows == 1


def test_not_null_check_catches_null(cfg: Config, built, tmp_path):
    import shutil

    corrupt = tmp_path / "null.duckdb"
    shutil.copy(cfg.warehouse_path, corrupt)
    con = duckdb.connect(str(corrupt))
    try:
        con.execute("UPDATE marts.dim_customers SET email = NULL WHERE customer_id = 1")
        result = NotNull("marts.dim_customers", "email").run(con)
    finally:
        con.close()
    assert not result.passed
    assert result.failing_rows == 1


def test_accepted_values_catches_bad_status(cfg: Config, built, tmp_path):
    import shutil

    corrupt = tmp_path / "status.duckdb"
    shutil.copy(cfg.warehouse_path, corrupt)
    con = duckdb.connect(str(corrupt))
    try:
        con.execute("UPDATE marts.fct_orders SET status = 'bogus' WHERE order_id = 1")
        result = AcceptedValues(
            "marts.fct_orders", "status",
            ["completed", "shipped", "cancelled", "returned"],
        ).run(con)
    finally:
        con.close()
    assert not result.passed
    assert result.failing_rows == 1


def test_suite_is_declarative(cfg: Config):
    """build_suite returns runnable Check objects covering all check kinds."""
    kinds = {c.kind for c in build_suite(cfg)}
    assert {
        "unique", "not_null", "accepted_values",
        "relationships", "row_count_min", "freshness",
    } <= kinds
