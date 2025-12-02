-- Athena table for Trust Stack run metadata
CREATE EXTERNAL TABLE IF NOT EXISTS truststack_runs (
  id BIGINT,
  external_id STRING,
  brand_id BIGINT,
  scenario_id BIGINT,
  status STRING,
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  config MAP<STRING, STRING>,
  error_message STRING
)
PARTITIONED BY (
  brand_slug STRING,
  year STRING,
  month STRING,
  day STRING
)
STORED AS PARQUET
LOCATION 's3://truststack-data/analytics/runs/'
TBLPROPERTIES (
  'parquet.compress'='SNAPPY'
);
