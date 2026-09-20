from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REQUIRED_ORDERS = {"order_id", "customer", "order_total"}
REQUIRED_PAYMENTS = {"payment_id", "order_id", "amount_paid", "status"}


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} is missing required columns: {sorted(missing)}")


def _clean_id(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper()


def reconcile(orders_path: Path, payments_path: Path, output_dir: Path) -> dict[str, float | int]:
    orders = pd.read_csv(orders_path)
    payments = pd.read_csv(payments_path)
    _require_columns(orders, REQUIRED_ORDERS, "orders")
    _require_columns(payments, REQUIRED_PAYMENTS, "payments")

    orders = orders.copy()
    payments = payments.copy()
    orders["order_id"] = _clean_id(orders["order_id"])
    payments["order_id"] = _clean_id(payments["order_id"])
    payments["status"] = payments["status"].astype("string").str.strip().str.lower()

    orders["order_total"] = pd.to_numeric(orders["order_total"], errors="coerce")
    payments["amount_paid"] = pd.to_numeric(payments["amount_paid"], errors="coerce")
    if orders["order_total"].isna().any():
        raise ValueError("orders contains invalid order_total values")
    if payments["amount_paid"].isna().any():
        raise ValueError("payments contains invalid amount_paid values")

    duplicate_payment_rows = int(payments.duplicated(subset=["payment_id"], keep="first").sum())
    payments = payments.drop_duplicates(subset=["payment_id"], keep="first")
    successful = payments[payments["status"].eq("paid")]

    paid_by_order = (
        successful.groupby("order_id", as_index=False)["amount_paid"]
        .sum()
        .rename(columns={"amount_paid": "paid_total"})
    )

    report = orders.merge(paid_by_order, on="order_id", how="left")
    report["paid_total"] = report["paid_total"].fillna(0.0)
    report["balance"] = (report["order_total"] - report["paid_total"]).round(2)

    conditions = [
        report["paid_total"].eq(0),
        report["balance"].gt(0) & report["paid_total"].gt(0),
        report["balance"].lt(0),
    ]
    labels = ["unpaid", "underpaid", "overpaid"]
    report["reconciliation_status"] = "matched"
    for condition, label in zip(conditions, labels, strict=True):
        report.loc[condition, "reconciliation_status"] = label

    orphan_payments = successful.loc[~successful["order_id"].isin(orders["order_id"]), "payment_id"]

    summary = {
        "orders": int(len(report)),
        "matched": int(report["reconciliation_status"].eq("matched").sum()),
        "exceptions": int(report["reconciliation_status"].ne("matched").sum()),
        "orphan_payments": int(orphan_payments.nunique()),
        "duplicate_payment_rows_removed": duplicate_payment_rows,
        "order_value": float(report["order_total"].sum().round(2)),
        "paid_value": float(report["paid_total"].sum().round(2)),
        "open_balance": float(report["balance"].sum().round(2)),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report.sort_values("order_id").to_csv(output_dir / "reconciliation.csv", index=False)
    report[report["reconciliation_status"].ne("matched")].sort_values("order_id").to_csv(
        output_dir / "exceptions.csv", index=False
    )
    pd.DataFrame([summary]).to_csv(output_dir / "summary.csv", index=False)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile order and payment exports.")
    parser.add_argument("--orders", type=Path, required=True)
    parser.add_argument("--payments", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()

    summary = reconcile(args.orders, args.payments, args.output_dir)
    print("Reconciliation complete")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
