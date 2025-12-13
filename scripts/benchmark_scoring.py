
import time
import json
import logging
import os
from dataclasses import dataclass
from typing import List, Dict, Any
from data.models import NormalizedContent
from scoring.scorer import ContentScorer
from config.settings import SETTINGS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_mock_content_batch() -> List[NormalizedContent]:
    """Create a mix of 'junk' and 'valid' content."""
    batch = []
    
    # 1. Very short junk (should be skipped)
    batch.append(NormalizedContent(
        content_id="junk_1",
        body="Requires login.",
        title="Login",
        url="http://example.com/login",
        src="web",
        platform_id="http://example.com/login",
        author="Unknown"
    ))
    
    # 2. Functional junk (should be skipped)
    batch.append(NormalizedContent(
        content_id="junk_2",
        body="Forgot your password? Enter your email to reset. " * 5, # < ~250 chars
        title="Reset Password",
        url="http://example.com/reset",
        src="web",
        platform_id="http://example.com/reset",
        author="Unknown"
    ))
    
    # 3. Valid short content (might be borderline, depending on rules)
    # The current rule says < 100 chars is skipped.
    batch.append(NormalizedContent(
        content_id="valid_short",
        body="This is a short but valid update about our product launch. It contains useful information." * 2,
        title="Product Update",
        url="http://example.com/news",
        src="web",
        platform_id="http://example.com/news",
        author="Unknown"
    ))
    
    # 4. Valid long content (should be scored)
    batch.append(NormalizedContent(
        content_id="valid_long",
        body="This is a comprehensive article about sustainability. " * 50,
        title="Sustainability Report",
        url="http://example.com/sustainability",
        src="web",
        platform_id="http://example.com/sustainability",
        author="Unknown"
    ))
    
    return batch

def run_benchmark(enable_triage: bool):
    """Run scoring benchmark."""
    logger.info(f"\n--- Running Benchmark with Triage {'ENABLED' if enable_triage else 'DISABLED'} ---")
    
    # Override settings
    SETTINGS['triage_enabled'] = enable_triage
    
    # Initialize scorer (mock LLM to avoid costs if possible, or rely on dry run)
    # Since we can't easily mock the internal LLM client here without patching, 
    # we assume the environment has API keys or we accept some cost/latency.
    # For a true benchmark, we want to see the skipped items return instantly.
    
    scorer = ContentScorer(use_attribute_detection=False) # Disable attribute sync to speed up
    
    content_batch = create_mock_content_batch()
    
    start_time = time.time()
    
    results = []
    for content in content_batch:
        # Mock brand context
        brand_context = {"keywords": ["sustainability", "product"], "brand_name": "ExampleBrand"}
        
        # Score
        item_start = time.time()
        score = scorer.score_content(content, brand_context)
        duration = time.time() - item_start
        
        triage_status = content.meta.get('triage_status', 'scored') if content.meta else 'scored'
        triage_reason = content.meta.get('triage_reason', '') if content.meta else ''
        
        results.append({
            "id": content.content_id,
            "status": triage_status,
            "reason": triage_reason,
            "duration": duration,
            "overall_score": score.overall
        })
        
    total_time = time.time() - start_time
    
    # Print Report
    print(f"\nResults (Triage={enable_triage}):")
    print(f"{'ID':<15} | {'Status':<10} | {'Duration (s)':<12} | {'Reason'}")
    print("-" * 60)
    for r in results:
        print(f"{r['id']:<15} | {r['status']:<10} | {r['duration']:<12.4f} | {r['reason']}")
    print("-" * 60)
    print(f"Total Time: {total_time:.4f}s")
    
    return results

if __name__ == "__main__":
    # 1. Run with Triage Disabled
    run_benchmark(enable_triage=False)
    
    # 2. Run with Triage Enabled
    run_benchmark(enable_triage=True)
