
import sys
import os
sys.path.append(os.getcwd())

from scoring.triage import triage_score_item, triage_filter
from data.models import NormalizedContent
from datetime import datetime

def create_dummy_content(body, title="Test Title", src="web"):
    return NormalizedContent(
        content_id="test_id",
        src=src,
        title=title,
        body=body,
        url="http://example.com",
        event_ts=datetime.now().isoformat(),
        platform_id="pid",
        author="author"
    )

def test_triage_flaw():
    print("Testing Triage Logic Flaws...")
    
    brand_keywords = ["Nike"]
    
    # Case 1: Relevant content but no brand keyword
    # e.g. a review of "Air Jordans" (which implies Nike but might not say "Nike")
    # or a general shoe review.
    body_no_brand = "This is a great running shoe. It has excellent cushioning and support. " * 5 # > 30 words
    content_no_brand = create_dummy_content(body_no_brand, title="Running Shoe Review")
    
    score = triage_score_item(content_no_brand, brand_keywords)
    print(f"Case 1 (No Brand Keyword): Score = {score}")
    
    if score < 0.45:
        print("  -> DEMOTED (Unexpected if relevant)")
    else:
        print("  -> PROMOTED (Fixed!)")

    # Case 2: Short content with brand keyword
    body_short = "Nike shoes are great."
    content_short = create_dummy_content(body_short, title="Short Review")
    
    score = triage_score_item(content_short, brand_keywords)
    print(f"Case 2 (Short + Brand Keyword): Score = {score}")
    # Base 0.5 + 0.2 (brand) - 0.1 (short) = 0.6 -> Promoted
    
    if score < 0.45:
        print("  -> DEMOTED")
    else:
        print("  -> PROMOTED")

    # Case 3: Competitor mention (relevant context) but no brand keyword
    body_competitor = "Adidas boosts are comfortable." * 5
    content_competitor = create_dummy_content(body_competitor, title="Adidas Review")
    
    score = triage_score_item(content_competitor, brand_keywords)
    print(f"Case 3 (Competitor Content): Score = {score}")
    
    if score < 0.45:
        print("  -> DEMOTED")
    else:
        print("  -> PROMOTED (Fixed!)")

if __name__ == "__main__":
    test_triage_flaw()
