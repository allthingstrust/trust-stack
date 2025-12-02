-- Athena table for Trust Stack dimension scores
CREATE EXTERNAL TABLE IF NOT EXISTS truststack_scores (
  id BIGINT,
  asset_id BIGINT,
  score_provenance DOUBLE,
  score_verification DOUBLE,
  score_transparency DOUBLE,
  score_coherence DOUBLE,
  score_resonance DOUBLE,
  score_ai_readiness DOUBLE,
  overall_score DOUBLE,
  classification STRING,
  rationale MAP<STRING, STRING>,
  flags MAP<STRING, STRING>,
  created_at TIMESTAMP
)
PARTITIONED BY (
  brand_slug STRING,
  year STRING,
  month STRING,
  day STRING
)
STORED AS PARQUET
LOCATION 's3://truststack-data/analytics/scores/'
TBLPROPERTIES (
  'parquet.compress'='SNAPPY'
);
