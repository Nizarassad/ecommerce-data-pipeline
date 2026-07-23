-- customer_lifetime_value: analytics mart, one row per customer.
-- Rolls fct_orders up to the customer and enriches with dimension attributes.
-- Only valid sales count toward lifetime value. Customers with no valid orders
-- still appear (LEFT JOIN) with zeroed metrics -- useful for retention/LTV work.
CREATE OR REPLACE TABLE marts.customer_lifetime_value AS
WITH per_customer AS (
    SELECT
        customer_id,
        COUNT(*) FILTER (WHERE is_valid_sale)              AS valid_orders,
        SUM(net_revenue)                                   AS lifetime_revenue,
        MIN(order_date) FILTER (WHERE is_valid_sale)       AS first_order_date,
        MAX(order_date) FILTER (WHERE is_valid_sale)       AS last_order_date
    FROM marts.fct_orders
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.email,
    c.country,
    c.segment,
    COALESCE(p.valid_orders, 0)                            AS valid_orders,
    COALESCE(p.lifetime_revenue, 0)                        AS lifetime_revenue,
    CAST(
        COALESCE(p.lifetime_revenue, 0)
        / NULLIF(p.valid_orders, 0) AS DECIMAL(12, 2)
    )                                                      AS avg_order_value,
    p.first_order_date,
    p.last_order_date
FROM marts.dim_customers c
LEFT JOIN per_customer p USING (customer_id);
