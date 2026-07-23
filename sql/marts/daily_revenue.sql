-- daily_revenue: analytics mart, one row per calendar day.
-- Time series of valid-sale revenue, order volume and unique buyers -- the kind
-- of table a BI dashboard or a forecasting model would sit on top of.
CREATE OR REPLACE TABLE marts.daily_revenue AS
SELECT
    order_date,
    COUNT(*) FILTER (WHERE is_valid_sale)          AS orders,
    COUNT(DISTINCT customer_id)
        FILTER (WHERE is_valid_sale)               AS buyers,
    SUM(net_revenue)                               AS revenue,
    CAST(
        SUM(net_revenue)
        / NULLIF(COUNT(*) FILTER (WHERE is_valid_sale), 0) AS DECIMAL(12, 2)
    )                                              AS avg_order_value
FROM marts.fct_orders
GROUP BY order_date
ORDER BY order_date;
