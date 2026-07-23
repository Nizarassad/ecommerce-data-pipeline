"""Deterministic synthetic e-commerce data generator.

Given a fixed seed, this produces the SAME raw files every time (verified by a
test). The output intentionally contains a little "dirt" -- exact-duplicate
customer rows, untrimmed / mixed-case emails, and un-normalised order statuses
-- so the staging layer has real cleaning work to do. Referential integrity is
kept intact in the generated data (every FK resolves); the quality layer and
tests prove that, and a test injects an orphan row to prove the checks bite.

Raw files are written in a mix of CSV and Parquet on purpose, to show the
ingest layer handling both:

    customers.csv        products.csv
    orders.parquet       order_items.parquet        events.parquet
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from edp.config import Config

# Reference "today" the synthetic world is anchored to. Order timestamps land in
# the ~180 days before this, and the most recent order is pinned to be fresh so
# the freshness quality check has a deterministic, passing target.
REFERENCE_DATE = datetime(2026, 7, 23)

COUNTRIES = ["US", "GB", "DE", "FR", "CA", "AU", "NL", "ES"]
SEGMENTS = ["consumer", "smb", "enterprise"]
CATEGORIES = ["Apparel", "Electronics", "Home", "Beauty", "Sports", "Books", "Toys"]
CHANNELS = ["web", "ios", "android", "marketplace"]
# Raw statuses are deliberately messy (case / whitespace); staging normalises.
RAW_STATUSES = ["completed", "COMPLETED ", " shipped", "Shipped", "cancelled", "returned"]
EVENT_TYPES = ["view", "add_to_cart", "purchase"]


@dataclass
class GenerateResult:
    """Row counts of what was written -- surfaced in the run summary."""

    counts: dict[str, int]
    paths: dict[str, str]


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _make_customers(cfg: Config, rng: np.random.Generator) -> pd.DataFrame:
    n = cfg.n_customers
    ids = np.arange(1, n + 1)
    first = rng.choice(
        ["Ava", "Liam", "Noah", "Emma", "Olivia", "Ethan", "Mia", "Lucas", "Zoe", "Leo"],
        size=n,
    )
    last = rng.choice(
        ["Smith", "Khan", "Garcia", "Muller", "Dubois", "Rossi", "Chen", "Kim", "Silva", "Adams"],
        size=n,
    )
    # Emails carry intentional dirt: random leading/trailing space and case, so
    # staging has to TRIM + LOWER them. The "clean" email is deterministic.
    dirt_space = rng.choice(["", " ", "  "], size=n, p=[0.8, 0.15, 0.05])
    dirt_upper = rng.random(n) < 0.1
    emails = []
    for i in range(n):
        base = f"{first[i]}.{last[i]}{ids[i]}@example.com"
        base = base.upper() if dirt_upper[i] else base
        emails.append(f"{dirt_space[i]}{base}{dirt_space[i]}")

    signup_offset = rng.integers(0, 720, size=n)
    signup = [REFERENCE_DATE - timedelta(days=int(d)) for d in signup_offset]

    df = pd.DataFrame(
        {
            "customer_id": ids,
            "first_name": first,
            "last_name": last,
            "email": emails,
            "country": rng.choice(COUNTRIES, size=n),
            "segment": rng.choice(SEGMENTS, size=n, p=[0.7, 0.22, 0.08]),
            "signup_date": [d.date().isoformat() for d in signup],
        }
    )

    # Inject exact-duplicate customer rows (~2%) for staging dedup to remove.
    dup_idx = rng.choice(ids, size=max(1, n // 50), replace=False) - 1
    dups = df.iloc[dup_idx].copy()
    df = pd.concat([df, dups], ignore_index=True)
    return df


def _make_products(cfg: Config, rng: np.random.Generator) -> pd.DataFrame:
    n = cfg.n_products
    ids = np.arange(1, n + 1)
    price = np.round(rng.uniform(5, 400, size=n), 2)
    # Cost is 40-80% of price -> positive but variable margins.
    cost = np.round(price * rng.uniform(0.4, 0.8, size=n), 2)
    return pd.DataFrame(
        {
            "product_id": ids,
            "product_name": [f"SKU-{i:04d}" for i in ids],
            "category": rng.choice(CATEGORIES, size=n),
            "price": price,
            "cost": cost,
        }
    )


def _make_orders_and_items(
    cfg: Config, rng: np.random.Generator, products: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = cfg.n_orders
    order_ids = np.arange(1, n + 1)
    customer_ids = rng.integers(1, cfg.n_customers + 1, size=n)

    # Order timestamps in the 180 days before the reference date...
    offsets = rng.integers(0, 180, size=n).astype(float)
    offsets += rng.random(n)  # fractional day -> a time-of-day component
    order_ts = [REFERENCE_DATE - timedelta(days=float(o)) for o in offsets]
    # ...but force order #1's timestamp to be fresh (today) so the freshness
    # check has a deterministic passing target regardless of random draws.
    order_ts[0] = REFERENCE_DATE - timedelta(hours=3)

    orders = pd.DataFrame(
        {
            "order_id": order_ids,
            "customer_id": customer_ids,
            "order_ts": [t.isoformat(sep=" ", timespec="seconds") for t in order_ts],
            "status": rng.choice(RAW_STATUSES, size=n),
            "channel": rng.choice(CHANNELS, size=n),
        }
    )

    # 1-5 line items per order.
    n_items = rng.integers(1, 6, size=n)
    rows = []
    prod_ids = products["product_id"].to_numpy()
    prod_price = dict(zip(products["product_id"], products["price"], strict=True))
    item_id = 1
    for i in range(n):
        chosen = rng.choice(prod_ids, size=int(n_items[i]), replace=False)
        for pid in chosen:
            qty = int(rng.integers(1, 4))
            # Sold price = list price with occasional small discount.
            discount = float(rng.choice([1.0, 0.9, 0.8], p=[0.8, 0.15, 0.05]))
            unit_price = round(prod_price[pid] * discount, 2)
            rows.append(
                {
                    "order_item_id": item_id,
                    "order_id": int(order_ids[i]),
                    "product_id": int(pid),
                    "quantity": qty,
                    "unit_price": unit_price,
                }
            )
            item_id += 1
    order_items = pd.DataFrame(rows)
    return orders, order_items


def _make_events(
    cfg: Config, rng: np.random.Generator, orders: pd.DataFrame, products: pd.DataFrame
) -> pd.DataFrame:
    """A simple browse -> add_to_cart -> purchase funnel per order, plus extra
    browsing noise, so events > orders and funnel analytics are possible."""
    prod_ids = products["product_id"].to_numpy()
    rows = []
    event_id = 1
    for _, o in orders.iterrows():
        session = f"s{o['order_id']}"
        base_ts = datetime.fromisoformat(o["order_ts"])
        # 1-4 views before the purchase.
        for k in range(int(rng.integers(1, 5))):
            rows.append(
                {
                    "event_id": event_id,
                    "customer_id": int(o["customer_id"]),
                    "session_id": session,
                    "event_ts": (base_ts - timedelta(minutes=30 - k)).isoformat(sep=" "),
                    "event_type": "view",
                    "product_id": int(rng.choice(prod_ids)),
                }
            )
            event_id += 1
        for etype, delta in (("add_to_cart", 10), ("purchase", 0)):
            rows.append(
                {
                    "event_id": event_id,
                    "customer_id": int(o["customer_id"]),
                    "session_id": session,
                    "event_ts": (base_ts - timedelta(minutes=delta)).isoformat(sep=" "),
                    "event_type": etype,
                    "product_id": int(rng.choice(prod_ids)),
                }
            )
            event_id += 1
    return pd.DataFrame(rows)


def generate(cfg: Config | None = None) -> GenerateResult:
    """Generate all raw files deterministically and return their row counts."""
    cfg = cfg or Config()
    cfg.ensure_dirs()
    rng = _rng(cfg.seed)

    customers = _make_customers(cfg, rng)
    products = _make_products(cfg, rng)
    orders, order_items = _make_orders_and_items(cfg, rng, products)
    events = _make_events(cfg, rng, orders, products)

    paths = {
        "customers": str(cfg.raw_dir / "customers.csv"),
        "products": str(cfg.raw_dir / "products.csv"),
        "orders": str(cfg.raw_dir / "orders.parquet"),
        "order_items": str(cfg.raw_dir / "order_items.parquet"),
        "events": str(cfg.raw_dir / "events.parquet"),
    }

    customers.to_csv(paths["customers"], index=False)
    products.to_csv(paths["products"], index=False)
    orders.to_parquet(paths["orders"], index=False)
    order_items.to_parquet(paths["order_items"], index=False)
    events.to_parquet(paths["events"], index=False)

    counts = {
        "customers": len(customers),  # includes injected duplicates
        "products": len(products),
        "orders": len(orders),
        "order_items": len(order_items),
        "events": len(events),
    }
    return GenerateResult(counts=counts, paths=paths)


if __name__ == "__main__":  # pragma: no cover
    res = generate()
    for name, c in res.counts.items():
        print(f"{name:12s} {c:>8,} rows")
