
import sys
import os
sys.path.append(os.getcwd())

from scoring.attribute_detector import TrustStackAttributeDetector
from scoring.signal_mapper import SignalMapper
from scoring.aggregator import ScoringAggregator
from data.models import NormalizedContent
import yaml

def test_provenance_scoring():
    # Load config
    with open('scoring/config/trust_signals.yml', 'r') as f:
        config = yaml.safe_load(f)
    
    detector = TrustStackAttributeDetector()
    mapper = SignalMapper(config)
    aggregator = ScoringAggregator(config)
    
    # Create neutral content
    content = NormalizedContent(
        content_id="test_content",
        url="https://www.unknown-brand.com/some-page",
        title="Test Page",
        body="This is a test page body with some content.",
        src="unknown-brand.com",
        author="John Doe",
        published_at="2024-01-01T00:00:00Z",
        platform_id="web",
        meta={
            "domain": "unknown-brand.com",
            # No red flags, no green flags
            "ssl_valid": "true",
            "has_privacy_policy": "true",
            "domain_age_days": 300
        }
    )
    
    print(f"Testing content from: {content.url}")
    
    # run detection
    attributes = detector.detect_attributes(content)
    print(f"\nDetected {len(attributes)} attributes:")
    for attr in attributes:
        print(f" - {attr.attribute_id}: {attr.value}")
        
    # map to signals
    signals = mapper.map_attributes_to_signals(attributes)

    # Simulate LLM-generated signal (prov_source_clarity) which is normally present
    from scoring.types import SignalScore
    signals.append(SignalScore(
        id="prov_source_clarity", 
        label="Source Attribution", 
        dimension="Provenance", 
        value=0.8, 
        weight=0.2, 
        evidence=["Simulated LLM signal"], 
        rationale="Simulated", 
        confidence=1.0
    ))

    print(f"\nMapped {len(signals)} signals:")
    prov_signals = [s for s in signals if s.dimension == 'Provenance']
    for s in prov_signals:
        print(f" - {s.id}: {s.value}")
        
    # Check for missing core signals
    prov_signal_ids = [s.id for s in prov_signals]
    core_signals = ['prov_author_bylines', 'prov_source_clarity', 'prov_domain_trust']
    
    missing = [c for c in core_signals if c not in prov_signal_ids]
    print(f"\nMissing core signals: {missing}")
    
    # Calculate score
    dim_score = aggregator.aggregate_dimension("Provenance", signals)
    print(f"\nProvenance Score: {dim_score.value}")
    print(f"Coverage: {dim_score.coverage}")
    
    if "prov_domain_trust" in missing and dim_score.value <= 6.0:
        print("\nFAILURE CONFIRMED: prov_domain_trust is missing and score is capped at 6.0")
    else:
        print("\nIssue not reproduced or different than expected.")

if __name__ == "__main__":
    test_provenance_scoring()
