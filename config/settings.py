"""
Main configuration settings for AR tool
"""

import os
from typing import Dict, List, Any
from dataclasses import dataclass
from dotenv import load_dotenv

# Load local .env file if present so os.getenv reads local secrets during dev
load_dotenv()

# Helper function to get secrets from Streamlit Cloud or environment variables
def get_secret(key: str, default: str = '') -> str:
    """
    Get secret from Streamlit Cloud secrets (if available) or environment variables.
    This allows the app to work both locally and on Streamlit Cloud.
    Always returns a string, converting booleans/numbers from TOML if needed.
    """
    try:
        import streamlit as st
        # Try to get from Streamlit secrets first (for cloud deployment)
        if hasattr(st, 'secrets') and key in st.secrets:
            value = st.secrets[key]
            # Convert to string if it's a boolean or number from TOML
            if isinstance(value, bool):
                return str(value)  # True -> "True", False -> "False"
            elif isinstance(value, (int, float)):
                return str(value)  # 1 -> "1", 1.0 -> "1.0"
            return value
    except (ImportError, FileNotFoundError):
        # Streamlit not available or secrets.toml not found - use environment variables
        pass
    
    # Fallback to environment variables (for local development)
    return os.getenv(key, default)

@dataclass
class ScoringWeights:
    """5D Trust Dimension weights"""
    provenance: float = 0.2
    verification: float = 0.2
    transparency: float = 0.2
    coherence: float = 0.2
    resonance: float = 0.2

@dataclass
class APIConfig:
    """API configurations for data sources"""
    reddit_client_id: str = get_secret('REDDIT_CLIENT_ID', '')
    reddit_client_secret: str = get_secret('REDDIT_CLIENT_SECRET', '')
    reddit_user_agent: str = get_secret('REDDIT_USER_AGENT', 'AR-Tool/1.0')

    # Amazon Product Advertising API
    amazon_access_key: str = get_secret('AMAZON_ACCESS_KEY', '')
    amazon_secret_key: str = get_secret('AMAZON_SECRET_KEY', '')
    amazon_associate_tag: str = get_secret('AMAZON_ASSOCIATE_TAG', '')

    # LLM API Keys
    openai_api_key: str = get_secret('OPENAI_API_KEY', '')
    anthropic_api_key: str = get_secret('ANTHROPIC_API_KEY', '')
    google_api_key: str = get_secret('GOOGLE_API_KEY', '')
    deepseek_api_key: str = get_secret('DEEPSEEK_API_KEY', '')

    # YouTube Data API v3
    youtube_api_key: str = get_secret('YOUTUBE_API_KEY', '')

    # Search Provider APIs
    brave_api_key: str = get_secret('BRAVE_API_KEY', '')
    serper_api_key: str = get_secret('SERPER_API_KEY', '')
    search_provider: str = get_secret('SEARCH_PROVIDER', 'serper')

# Global settings
SETTINGS = {
    'app_name': 'Trust Stack Rating Tool',
    'version': '2.0.0-trust-stack',
    'debug': get_secret('DEBUG', 'False').lower() == 'true',

    # Trust Stack Rating configuration
    'scoring_weights': ScoringWeights(),
    'rubric_version': 'v2.0-trust-stack',

    # Legacy AR thresholds (kept for backward compatibility and optional descriptive bands)
    'min_score_threshold': 0.75,  # 75/100 - Excellent/Authentic threshold
    'suspect_threshold': 0.40,    # 40/100 - Fair/Suspect threshold

    # Rating bands (optional descriptive labels, not used for AR calculation)
    'rating_scale': 100,  # 0-100 scale for all ratings
    'rating_bands': {
        'excellent': 80,  # >= 80 = Excellent
        'good': 60,       # 60-79 = Good
        'fair': 40,       # 40-59 = Fair
        'poor': 0,        # < 40 = Poor
    },

    # Feature flags
    'enable_legacy_ar_mode': True,  # Synthesize AR from ratings for backward compatibility
    'show_ar_in_ui': False,  # Don't show AR in initial UI (can enable later)
    
    # Content processing
    'max_content_length': 10000,  # Characters
    'deduplication_window': 24,   # Hours for SimHash deduplication
    'batch_size': 100,
    
    # API rate limits
    'reddit_rate_limit': 60,      # requests per minute
    'amazon_rate_limit': 1,       # requests per second
    'openai_rate_limit': 60,      # requests per minute
    'youtube_rate_limit': 60,    # requests per minute (YouTube Data API key quota should be considered)
    
    # Data retention
    'data_retention_days': 90,
    'max_runs_per_brand': 1000,
    
    # Reporting
    'report_formats': ['pdf', 'markdown', 'json'],
    'default_report_format': 'pdf',
    'include_charts': True,
    'chart_format': 'png',
    # Triage configuration: enable cheap triage before LLM scoring
    'triage_enabled': str(get_secret('AR_TRIAGE_ENABLED', 'False')).lower() == 'true',
    'triage_promote_threshold': 0.6,
    # When true, items demoted by triage are excluded from S3 uploads and reports
    'exclude_demoted_from_upload': False,
    # Global control: whether to include parsed comments in the analysis
    'include_comments_in_analysis': False,
    # Brands to explicitly exclude from automated review (comma-separated env var or list)
    'excluded_brands': [b.strip().lower() for b in get_secret('EXCLUDED_BRANDS', '').split(',') if b.strip()],
    
    # Visual Analysis configuration
    'visual_analysis_enabled': str(get_secret('VISUAL_ANALYSIS_ENABLED', 'false')).lower() == 'true',
    'visual_analysis_model': get_secret('VISUAL_ANALYSIS_MODEL', 'gemini-2.0-flash'),
    'visual_scope': get_secret('VISUAL_SCOPE', 'brand_owned,landing_page'),
    'screenshot_s3_bucket': get_secret('SCREENSHOT_S3_BUCKET', ''),
    'report_s3_bucket': get_secret('REPORT_S3_BUCKET', ''), # Dedicated bucket for public report images
    'screenshot_s3_prefix': get_secret('SCREENSHOT_S3_PREFIX', 'visual-analysis/'),
    'screenshot_retention_hours': int(get_secret('SCREENSHOT_RETENTION_HOURS', '24')),
}

# URL Collection Ratio Configuration
@dataclass
class URLCollectionRatioConfig:
    """Configuration for brand-owned vs 3rd party URL ratio (60/40 recommended)"""
    brand_owned_ratio: float = 0.6
    third_party_ratio: float = 0.4

    # Brand identification (should be set per brand analysis)
    brand_domains: list = None
    brand_subdomains: list = None
    brand_social_handles: list = None

    def __post_init__(self):
        if self.brand_domains is None:
            self.brand_domains = []
        if self.brand_subdomains is None:
            self.brand_subdomains = []
        if self.brand_social_handles is None:
            self.brand_social_handles = []

# Brand configuration templates
BRAND_TEMPLATES = {
    'default': {
        'keywords': [],
        'exclude_keywords': [],
        'sources': ['reddit', 'amazon', 'youtube', 'yelp'],
        'custom_scoring_weights': None,
        'url_collection_ratio': URLCollectionRatioConfig(),
    }
}

# Verification database endpoints
VERIFICATION_DBS = {
    'fda': 'https://api.fda.gov/',
    'sec': 'https://www.sec.gov/',
    'whois': 'https://whoisjson.com/',
    'c2pa': 'https://c2pa.org/',
}

def get_brand_config(brand_id: str) -> Dict[str, Any]:
    """Get configuration for a specific brand"""
    # In production, this would load from database or config files
    return BRAND_TEMPLATES.get('default', {}).copy()

def validate_config() -> List[str]:
    """Validate configuration and return any issues"""
    issues = []
    
    if not SETTINGS['scoring_weights'].provenance + \
           SETTINGS['scoring_weights'].verification + \
           SETTINGS['scoring_weights'].transparency + \
           SETTINGS['scoring_weights'].coherence + \
           SETTINGS['scoring_weights'].resonance == 1.0:
        issues.append("Scoring weights must sum to 1.0")
    
    if SETTINGS['min_score_threshold'] <= SETTINGS['suspect_threshold']:
        issues.append("Min score threshold must be greater than suspect threshold")
    
    return issues
