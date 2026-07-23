-- stg_orders: normalise messy raw order status and cast the timestamp.
--   Raw status values arrive as e.g. 'COMPLETED ', ' shipped', 'Shipped'.
--   We fold them to a small controlled vocabulary and derive an is_valid_sale
--   flag (cancelled / returned orders contribute no net revenue downstream).
CREATE OR REPLACE TABLE stg.stg_orders AS
SELECT
    CAST(order_id AS BIGINT)                 AS order_id,
    CAST(customer_id AS BIGINT)              AS customer_id,
    CAST(order_ts AS TIMESTAMP)              AS order_ts,
    CAST(order_ts AS DATE)                   AS order_date,
    LOWER(TRIM(status))                      AS status,
    LOWER(TRIM(status)) IN ('completed', 'shipped') AS is_valid_sale,
    TRIM(channel)                            AS channel
FROM raw.raw_orders;
