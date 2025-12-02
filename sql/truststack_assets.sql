-- Athena table for Trust Stack content assets
CREATE EXTERNAL TABLE IF NOT EXISTS truststack_assets (
  id BIGINT,
  run_id BIGINT,
  source_type STRING,
  channel STRING,
  url STRING,
  external_id STRING,
  title STRING,
  normalized_content STRING,
  modality STRING,
  language STRING,
  metadata MAP<STRING, STRING>,
  created_at TIMESTAMP
)
PARTITIONED BY (
  brand_slug STRING,
  year STRING,
  month STRING,
  day STRING
)
STORED AS PARQUET
LOCATION 's3://truststack-data/analytics/assets/'
TBLPROPERTIES (
  'parquet.compress'='SNAPPY'
);
