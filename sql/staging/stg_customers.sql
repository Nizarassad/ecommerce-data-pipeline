-- stg_customers: clean + dedupe raw customers.
--   * TRIM + LOWER the email (raw has stray whitespace and mixed case)
--   * cast signup_date TEXT -> DATE
--   * de-duplicate exact-duplicate rows injected in the raw feed, keeping one
--     row per customer_id (the natural key)
CREATE OR REPLACE TABLE stg.stg_customers AS
WITH cleaned AS (
    SELECT
        CAST(customer_id AS BIGINT)          AS customer_id,
        TRIM(first_name)                     AS first_name,
        TRIM(last_name)                      AS last_name,
        LOWER(TRIM(email))                   AS email,
        UPPER(TRIM(country))                 AS country,
        LOWER(TRIM(segment))                 AS segment,
        CAST(signup_date AS DATE)            AS signup_date
    FROM raw.raw_customers
),
deduped AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY email
        ) AS _rn
    FROM cleaned
)
SELECT
    customer_id, first_name, last_name, email, country, segment, signup_date
FROM deduped
WHERE _rn = 1;
