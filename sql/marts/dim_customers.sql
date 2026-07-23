-- dim_customers: the customer dimension of the star schema.
-- One row per customer (grain = customer_id). Sourced from the cleaned +
-- de-duplicated staging model, so this is already unique on customer_id.
CREATE OR REPLACE TABLE marts.dim_customers AS
SELECT
    customer_id,
    first_name,
    last_name,
    email,
    country,
    segment,
    signup_date
FROM stg.stg_customers;
