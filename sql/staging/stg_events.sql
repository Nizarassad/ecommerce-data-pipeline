-- stg_events: typecast the clickstream feed for downstream funnel analysis.
CREATE OR REPLACE TABLE stg.stg_events AS
SELECT
    CAST(event_id AS BIGINT)        AS event_id,
    CAST(customer_id AS BIGINT)     AS customer_id,
    CAST(session_id AS VARCHAR)     AS session_id,
    CAST(event_ts AS TIMESTAMP)     AS event_ts,
    LOWER(TRIM(event_type))         AS event_type,
    CAST(product_id AS BIGINT)      AS product_id
FROM raw.raw_events;
