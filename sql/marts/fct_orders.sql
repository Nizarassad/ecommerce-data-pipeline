-- fct_orders: the central fact table of the star schema.
-- Grain = one row per order_id. Order-header attributes are joined to the
-- aggregated line items to give gross revenue, units and item count per order.
-- net_revenue respects the sale validity flag (cancelled/returned -> 0), which
-- is what the revenue marts downstream sum.
CREATE OR REPLACE TABLE marts.fct_orders AS
WITH item_rollup AS (
    SELECT
        order_id,
        COUNT(*)                       AS item_count,
        SUM(quantity)                  AS units,
        SUM(line_revenue)              AS gross_revenue
    FROM stg.stg_order_items
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.customer_id,               -- FK -> dim_customers.customer_id
    o.order_ts,
    o.order_date,
    o.status,
    o.channel,
    o.is_valid_sale,
    COALESCE(i.item_count, 0)                        AS item_count,
    COALESCE(i.units, 0)                             AS units,
    COALESCE(i.gross_revenue, 0)                     AS gross_revenue,
    CASE WHEN o.is_valid_sale
         THEN COALESCE(i.gross_revenue, 0) ELSE 0 END AS net_revenue
FROM stg.stg_orders o
LEFT JOIN item_rollup i USING (order_id);
