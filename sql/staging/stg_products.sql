-- stg_products: typecast money columns and derive unit margin.
CREATE OR REPLACE TABLE stg.stg_products AS
SELECT
    CAST(product_id AS BIGINT)              AS product_id,
    TRIM(product_name)                      AS product_name,
    TRIM(category)                          AS category,
    CAST(price AS DECIMAL(10, 2))           AS price,
    CAST(cost  AS DECIMAL(10, 2))           AS cost,
    CAST(price - cost AS DECIMAL(10, 2))    AS unit_margin
FROM raw.raw_products;
