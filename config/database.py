"""
Database configuration for AR tool
AWS Athena and S3 settings
"""

import os
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database settings
DATABASE_CONFIG = {
    'database_name': 'ar_mvp',
    'workgroup': 'AR-MVP',
    'results_bucket': 's3://ar-athena-result/AR-MVP/',
    'data_bucket': 's3://ar-ingestion-normalized/',
    
    # Table names
    'normalized_table': 'ar_mvp.ar_content_normalized_v2',
    'scores_table': 'ar_mvp.ar_content_scores_v2',
    'view_name': 'ar_mvp.v_content_normalized',
    
    # Partition configuration
    'partition_scheme': ['brand_id', 'source'],
    'supported_sources': ['reddit', 'amazon', 'youtube', 'yelp', 'brave', 'serper'],
    
    # File format settings
    'file_format': 'PARQUET',
    'compression': 'SNAPPY',
}

# AWS credentials (set via environment variables)
AWS_CONFIG = {
    'region': os.getenv('AWS_REGION', 'us-east-1'),
    'access_key_id': os.getenv('AWS_ACCESS_KEY_ID'),
    'secret_access_key': os.getenv('AWS_SECRET_ACCESS_KEY'),
    'session_token': os.getenv('AWS_SESSION_TOKEN'),  # For temporary credentials
}

# Athena query settings
ATHENA_CONFIG = {
    'max_execution_time': 3600,  # 1 hour
    'output_location': DATABASE_CONFIG['results_bucket'],
    'encryption_configuration': {
        # boto3 expects 'EncryptionOption' (capitalized) and optional 'KmsKey'
        'EncryptionOption': 'SSE_S3'
    }
}

def get_database_connection_string() -> str:
    """Generate database connection string for boto3"""
    return f"awsathena+rest://{AWS_CONFIG['access_key_id']}:{AWS_CONFIG['secret_access_key']}@{AWS_CONFIG['region']}/?s3_staging_dir={DATABASE_CONFIG['results_bucket']}&work_group={DATABASE_CONFIG['workgroup']}"
