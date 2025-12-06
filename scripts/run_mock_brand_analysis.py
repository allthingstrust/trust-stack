
import sys
import os
import logging
from datetime import datetime
from typing import List

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.models import NormalizedContent
from scoring.scorer import ContentScorer
from scoring.types import TrustScore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_mock_brand_analysis():
    logger.info("Starting Mock Brand Analysis (End-to-End Verification)...")
    
    # 1. Define Mock Content
    # We simulate a crawl of 3 pages: Home, Blog, Product
    
    # Homepage: Has Privacy Policy, Contact Info
    homepage = NormalizedContent(
        content_id="home_1",
        src="web",
        platform_id="http://example.com",
        author="",
        title="Example Brand Home",
        body="""
        Welcome to Example Brand. We make great things.
        
        Contact Us: support@example.com
        Phone: 555-0123
        
        Privacy Policy | Terms of Service
        """,
        run_id="run_1",
        event_ts=datetime.now().isoformat(),
        meta={"url": "http://example.com"}
    )
    
    # Blog Post: Has Author Byline, AI Disclosure
    blog_post = NormalizedContent(
        content_id="blog_1",
        src="web",
        platform_id="http://example.com/blog/future-of-ai",
        author="", # Missing metadata author
        title="The Future of AI",
        body="""
        By Sarah Connor
        
        Artificial Intelligence is changing the world.
        
        This article was assisted by AI tools for research.
        """,
        run_id="run_1",
        event_ts=datetime.now().isoformat(),
        meta={"url": "http://example.com/blog/future-of-ai", "type": "blog"}
    )
    
    # Product Page: Has Reviews, C2PA (simulated via metadata)
    product_page = NormalizedContent(
        content_id="prod_1",
        src="web",
        platform_id="http://example.com/product/widget",
        author="",
        title="Super Widget 3000",
        body="""
        The best widget you'll ever buy.
        
        Customer Reviews
        Rated 4.8 out of 5 stars based on 250 reviews.
        
        "Amazing product!" - Verified Buyer
        """,
        run_id="run_1",
        event_ts=datetime.now().isoformat(),
        meta={
            "url": "http://example.com/product/widget", 
            "c2pa_manifest": "true", 
            "c2pa_valid": "true"
        }
    )
    
    contents = [homepage, blog_post, product_page]
    
    # 2. Initialize Scorer
    scorer = ContentScorer(use_attribute_detection=True)
    brand_context = {"keywords": ["widget", "ai"], "brand_name": "Example Brand"}
    
    # 3. Score Each Page
    page_scores: List[TrustScore] = []
    
    for content in contents:
        logger.info(f"Scoring {content.title} ({content.content_id})...")
        score = scorer.score_content(content, brand_context)
        page_scores.append(score)
        
        # Log detected signals for this page
        signals = []
        for dim in score.dimensions.values():
            signals.extend([s.id for s in dim.signals])
        logger.info(f"  -> Score: {score.overall:.1f}, Signals: {signals}")

    # 4. Aggregate Brand Score (Simple Average)
    # In the real app, this logic lives in AnalysisEngine or TrustStackReport
    total_score = sum(s.overall for s in page_scores) / len(page_scores)
    total_confidence = sum(s.confidence for s in page_scores) / len(page_scores)
    total_coverage = sum(s.coverage for s in page_scores) / len(page_scores)
    
    logger.info("="*50)
    logger.info(f"FINAL BRAND TRUST SCORE: {total_score:.1f} / 100")
    logger.info(f"Confidence: {total_confidence:.2f}")
    logger.info(f"Coverage: {total_coverage:.2f}")
    logger.info("="*50)
    
    # 5. Assertions
    if total_score <= 10.0:
        logger.error("❌ Score is too low! Calibration failed to lift score above baseline.")
        sys.exit(1)
        
    # Check for specific signals across the brand
    all_signals = set()
    for s in page_scores:
        for dim in s.dimensions.values():
            for sig in dim.signals:
                all_signals.add(sig.id)
                
    expected_signals = {
        "trans_contact_info", 
        "trans_disclosures", 
        "prov_author_bylines", 
        "trans_ai_labeling", 
        "ver_social_proof",
        "prov_metadata_c2pa"
    }
    
    missing = expected_signals - all_signals
    if missing:
        logger.warning(f"⚠️ Missing expected signals: {missing}")
    else:
        logger.info("✅ All expected signals detected across brand assets!")

if __name__ == "__main__":
    run_mock_brand_analysis()
