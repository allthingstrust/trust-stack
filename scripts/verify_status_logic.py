
import sys
import os
import logging
from typing import List, Dict, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.models import DetectedAttribute
from scoring.types import SignalScore, DimensionScore
from scoring.signal_mapper import SignalMapper
from scoring.aggregator import ScoringAggregator

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_status_logic")

def test_status_logic():
    print("Testing Status Logic in SignalMapper and Aggregator...")
    
    # Mock config
    config = {
        'signals': {
            'prov_author_bylines': {
                'id': 'prov_author_bylines',
                'label': 'Author Bylines',
                'dimension': 'Provenance',
                'weight': 1.0,
                'requirement_level': 'core'
            },
             'trans_ai_labeling': {
                'id': 'trans_ai_labeling',
                'label': 'AI Labeling',
                'dimension': 'Transparency',
                'weight': 1.0
            }
        },
        'dimensions': {
            'provenance': {'weight': 0.5},
            'transparency': {'weight': 0.5}
        }
    }
    
    mapper = SignalMapper(config)
    aggregator = ScoringAggregator(config)
    
    # Test Case 1: Present Attribute -> Valid Score
    print("\n--- Test Case 1: Present Attribute ---")
    attr_present = DetectedAttribute(
        attribute_id="author_brand_identity_verified",
        dimension="provenance",
        label="Author Verified",
        value=10.0,
        evidence="Found author",
        confidence=1.0,
        status="present",
        reason="Found"
    )
    signals_present = mapper.map_attributes_to_signals([attr_present])
    score_present = aggregator.aggregate_dimension("Provenance", signals_present)
    print(f"Present Score: {score_present.value}")
    assert score_present.value > 8.0, "Present signal should give high score"

    # Test Case 2: Absent Attribute -> Low Score
    print("\n--- Test Case 2: Absent Attribute ---")
    attr_absent = DetectedAttribute(
        attribute_id="author_brand_identity_verified",
        dimension="provenance",
        label="Author Verified",
        value=1.0,
        evidence="Not found",
        confidence=1.0,
        status="absent",
        reason="Not found"
    )
    signals_absent = mapper.map_attributes_to_signals([attr_absent])
    score_absent = aggregator.aggregate_dimension("Provenance", signals_absent)
    print(f"Absent Score: {score_absent.value}")
    assert score_absent.value < 4.0, "Absent signal should give low score"

    # Test Case 3: Unknown Attribute -> Neutral/Ignored Score (but satisfied presence)
    print("\n--- Test Case 3: Unknown Attribute ---")
    attr_unknown = DetectedAttribute(
        attribute_id="author_brand_identity_verified",
        dimension="provenance",
        label="Author Verified",
        value=1.0, # Value is low, BUT status is unknown
        evidence="Could not determine",
        confidence=0.5,
        status="unknown",
        reason="Ambiguous"
    )
    signals_unknown = mapper.map_attributes_to_signals([attr_unknown])
    
    # Note: If it's the ONLY signal, and we exclude it from weight, raw score is 0.0.
    # But we want to ensure it passes 'core deficit' checks.
    score_unknown = aggregator.aggregate_dimension("Provenance", signals_unknown)
    print(f"Unknown Score: {score_unknown.value}")
    
    # If the logic allows 'unknown' to pass as present, it shouldn't hit the 6.0 cap (core deficit).
    # Since raw score is 0.0 (no weighted signals), final might be 0.0?
    # Wait, if raw score is 0.0, then effective score is 0.0.
    # We need to distinguish "Unknown causing 0" vs "Absent causing 0".
    # If we have OTHER signals, 'unknown' shouldn't drag them down.
    
    # Let's add a second known signal to verify neutrality
    attr_other = DetectedAttribute(
        attribute_id="source_domain_trust_baseline",
        dimension="provenance",
        label="Domain Trust",
        value=10.0,
        evidence="Good domain",
        confidence=1.0,
        status="present"
    )
    # We need to map this manually or add to config to map it
    config['signals']['prov_domain_trust'] = {
        'id': 'prov_domain_trust',
        'dimension': 'Provenance',
        'weight': 1.0
    }
    # Reset objects with new config
    mapper = SignalMapper(config)
    aggregator = ScoringAggregator(config)
    
    signals_mixed = mapper.map_attributes_to_signals([attr_unknown, attr_other])
    score_mixed = aggregator.aggregate_dimension("Provenance", signals_mixed)
    print(f"Mixed Score (Unknown + Present): {score_mixed.value}")
    
    # If unknown was treated as absent (value=1.0), average would be (1.0 + 10.0) / 2 = 5.5
    # If unknown is excluded (neutral), average should be 10.0 / 1 = 10.0
    assert score_mixed.value > 9.0, f"Unknown signal should be ignored, expected > 9.0, got {score_mixed.value}"
    
    print("\nSUCCESS: Status logic verified!")

if __name__ == "__main__":
    test_status_logic()
