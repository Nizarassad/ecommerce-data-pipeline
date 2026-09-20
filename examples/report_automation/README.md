# Buyer-facing report automation example

A deliberately small example of the kind of business workflow that is often still handled manually in spreadsheets:

> take two recurring exports, clean the keys, reconcile them, flag exceptions, and produce a repeatable management-ready output.

This example is intentionally simpler than the main ELT project. The goal is to show the **last-mile automation pattern** a small business can inspect and maintain.

## Input

- `input/orders.csv` — order export
- `input/payments.csv` — payment export

The sample data deliberately contains inconsistent IDs, a partial payment, an overpayment, unpaid orders, a failed payment, an orphan payment and a duplicate payment row.

## Run

From the repository root after installing the project dependencies:

```bash
python examples/report_automation/reconcile_reports.py \
  --orders examples/report_automation/input/orders.csv \
  --payments examples/report_automation/input/payments.csv \
  --output-dir examples/report_automation/output
```

## Output

The script overwrites the same three outputs on every run, so rerunning it is safe and predictable:

- `reconciliation.csv` — one row per order with paid total, balance and status;
- `exceptions.csv` — only rows requiring review;
- `summary.csv` — compact management totals.

Expected sample summary:

| Metric | Value |
| --- | ---: |
| Orders | 5 |
| Matched | 1 |
| Exceptions | 4 |
| Orphan payments | 1 |
| Duplicate payment rows removed | 1 |
| Order value | 3,615.49 |
| Paid value applied to known orders | 2,600.50 |
| Net open balance | 1,014.99 |

## Why this is production-shaped rather than a spreadsheet trick

- validates required columns before processing;
- normalizes join keys before matching;
- coerces and validates numeric inputs;
- removes duplicate payment records deterministically;
- excludes failed payments from paid totals;
- distinguishes matched / unpaid / underpaid / overpaid orders;
- detects successful payments that do not map to a known order;
- produces a separate exception queue rather than hiding problems;
- contains no credentials, external services, or paid dependencies.

A real client version could replace the CSV inputs with Excel files, Google Sheets, APIs, scheduled downloads, email/Slack alerts or a BI dashboard. The reconciliation and validation pattern stays the same.

All sample names and amounts are synthetic.
