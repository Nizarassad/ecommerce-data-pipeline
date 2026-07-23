"""Data-quality test layer (a small, self-contained Great-Expectations / dbt-tests).

Each check is a declarative object that compiles to a single SQL query returning
a count of FAILING rows (0 = pass). This mirrors how dbt generic tests and GE
expectations work, but with zero extra dependencies so it runs anywhere the
warehouse runs. The suite runs against the ALREADY-BUILT warehouse and returns a
structured pass/fail report.

Check types:
    NotNull            - a column has no NULLs
    Unique             - a column (natural/primary key) has no duplicates
    AcceptedValues     - a column only contains values from an allow-list
    RelationshipsTest  - every FK value exists in the parent table (RI)
    RowCountMin        - a table has at least N rows
    Freshness          - the newest timestamp is within N days of a reference
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import duckdb

from edp.config import Config
from edp.generate import REFERENCE_DATE


@dataclass
class CheckResult:
    name: str
    kind: str
    passed: bool
    failing_rows: int
    detail: str = ""


class Check:
    """Base check. Subclasses implement `sql()` returning failing-row count."""

    kind = "base"

    def __init__(self, name: str):
        self.name = name

    def sql(self) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def run(self, con: duckdb.DuckDBPyConnection) -> CheckResult:
        failing = con.execute(self.sql()).fetchone()[0]
        return CheckResult(
            name=self.name,
            kind=self.kind,
            passed=(failing == 0),
            failing_rows=int(failing),
        )


class NotNull(Check):
    kind = "not_null"

    def __init__(self, table: str, column: str):
        super().__init__(f"not_null: {table}.{column}")
        self.table, self.column = table, column

    def sql(self) -> str:
        return f"SELECT count(*) FROM {self.table} WHERE {self.column} IS NULL"


class Unique(Check):
    kind = "unique"

    def __init__(self, table: str, column: str):
        super().__init__(f"unique: {table}.{column}")
        self.table, self.column = table, column

    def sql(self) -> str:
        # Count how many surplus rows exist beyond one-per-key.
        return (
            f"SELECT COALESCE(SUM(c - 1), 0) FROM ("
            f"  SELECT count(*) AS c FROM {self.table} "
            f"  GROUP BY {self.column} HAVING count(*) > 1"
            f")"
        )


class AcceptedValues(Check):
    kind = "accepted_values"

    def __init__(self, table: str, column: str, allowed: list[str]):
        super().__init__(f"accepted_values: {table}.{column}")
        self.table, self.column, self.allowed = table, column, allowed

    def sql(self) -> str:
        vals = ", ".join(f"'{v}'" for v in self.allowed)
        return f"SELECT count(*) FROM {self.table} WHERE {self.column} NOT IN ({vals})"


class RelationshipsTest(Check):
    """Referential integrity: every child FK must exist in the parent PK."""

    kind = "relationships"

    def __init__(self, child: str, fk: str, parent: str, pk: str):
        super().__init__(f"relationships: {child}.{fk} -> {parent}.{pk}")
        self.child, self.fk, self.parent, self.pk = child, fk, parent, pk

    def sql(self) -> str:
        return (
            f"SELECT count(*) FROM {self.child} c "
            f"LEFT JOIN {self.parent} p ON c.{self.fk} = p.{self.pk} "
            f"WHERE c.{self.fk} IS NOT NULL AND p.{self.pk} IS NULL"
        )


class RowCountMin(Check):
    kind = "row_count_min"

    def __init__(self, table: str, minimum: int):
        super().__init__(f"row_count_min({minimum}): {table}")
        self.table, self.minimum = table, minimum

    def sql(self) -> str:
        # Failing rows = 1 if below threshold, else 0.
        return f"SELECT CASE WHEN count(*) < {self.minimum} THEN 1 ELSE 0 END FROM {self.table}"


class Freshness(Check):
    """Newest timestamp must be within `max_age_days` of a reference instant."""

    kind = "freshness"

    def __init__(self, table: str, ts_column: str, max_age_days: int, reference: datetime):
        super().__init__(f"freshness({max_age_days}d): {table}.{ts_column}")
        self.table, self.ts_column = table, ts_column
        self.max_age_days, self.reference = max_age_days, reference

    def sql(self) -> str:
        ref = self.reference.isoformat(sep=" ")
        return (
            f"SELECT CASE WHEN date_diff('day', max({self.ts_column}), TIMESTAMP '{ref}') "
            f"> {self.max_age_days} THEN 1 ELSE 0 END FROM {self.table}"
        )


@dataclass
class QualityReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def n_passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def n_failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def as_table(self) -> str:
        lines = []
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            suffix = "" if r.passed else f"  ({r.failing_rows} bad rows)"
            lines.append(f"  [{status}] {r.name}{suffix}")
        return "\n".join(lines)


def build_suite(cfg: Config) -> list[Check]:
    """The declarative test suite that runs against the built marts.

    These are the guarantees the warehouse is expected to uphold; they read like
    a data contract for the star schema.
    """
    return [
        # --- Primary / natural key uniqueness -------------------------------
        Unique("marts.dim_customers", "customer_id"),
        Unique("marts.dim_products", "product_id"),
        Unique("marts.fct_orders", "order_id"),
        Unique("marts.customer_lifetime_value", "customer_id"),
        Unique("marts.daily_revenue", "order_date"),
        # --- Not-null on keys and critical measures -------------------------
        NotNull("marts.dim_customers", "customer_id"),
        NotNull("marts.dim_customers", "email"),
        NotNull("marts.fct_orders", "order_id"),
        NotNull("marts.fct_orders", "customer_id"),
        NotNull("marts.fct_orders", "net_revenue"),
        # --- Controlled vocabularies ----------------------------------------
        AcceptedValues(
            "marts.fct_orders", "status",
            ["completed", "shipped", "cancelled", "returned"],
        ),
        AcceptedValues(
            "marts.dim_customers", "segment",
            ["consumer", "smb", "enterprise"],
        ),
        # --- Referential integrity (the star-schema FKs) --------------------
        RelationshipsTest("marts.fct_orders", "customer_id", "marts.dim_customers", "customer_id"),
        RelationshipsTest(
            "stg.stg_order_items", "order_id", "marts.fct_orders", "order_id"
        ),
        RelationshipsTest(
            "stg.stg_order_items", "product_id", "marts.dim_products", "product_id"
        ),
        # --- Volume + freshness ---------------------------------------------
        RowCountMin("marts.fct_orders", 1),
        RowCountMin("marts.dim_customers", 1),
        Freshness("marts.fct_orders", "order_ts", cfg.freshness_max_age_days, REFERENCE_DATE),
    ]


def run_quality(cfg: Config | None = None) -> QualityReport:
    """Execute the whole suite against the warehouse and return the report."""
    cfg = cfg or Config()
    con = duckdb.connect(str(cfg.warehouse_path))
    report = QualityReport()
    try:
        for check in build_suite(cfg):
            report.results.append(check.run(con))
    finally:
        con.close()
    return report


if __name__ == "__main__":  # pragma: no cover
    rep = run_quality()
    print(rep.as_table())
    print(f"\n{rep.n_passed} passed, {rep.n_failed} failed")
