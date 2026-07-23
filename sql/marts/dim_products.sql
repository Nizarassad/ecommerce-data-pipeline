-- dim_products: the product dimension of the star schema.
-- Grain = product_id. Carries margin so product-level profitability is
-- available without re-deriving it in every downstream query.
CREATE OR REPLACE TABLE marts.dim_products AS
SELECT
    product_id,
    product_name,
    category,
    price,
    cost,
    unit_margin
FROM stg.stg_products;
