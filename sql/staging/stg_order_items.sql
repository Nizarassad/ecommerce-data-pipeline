-- stg_order_items: typecast and derive gross line revenue (qty * unit_price).
CREATE OR REPLACE TABLE stg.stg_order_items AS
SELECT
    CAST(order_item_id AS BIGINT)                       AS order_item_id,
    CAST(order_id AS BIGINT)                            AS order_id,
    CAST(product_id AS BIGINT)                          AS product_id,
    CAST(quantity AS INTEGER)                           AS quantity,
    CAST(unit_price AS DECIMAL(10, 2))                  AS unit_price,
    CAST(quantity * unit_price AS DECIMAL(12, 2))       AS line_revenue
FROM raw.raw_order_items;
