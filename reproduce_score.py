import sys
import os
import logging
from typing import List, Dict

# Setup basic logging
logging.basicConfig(level=logging.INFO)

# Add project root to path
sys.path.append(os.getcwd())

from scoring.aggregator import ScoringAggregator
from scoring.signal_mapper import SignalMapper
from scoring.types import SignalScore, DimensionScore
from data.models import DetectedAttribute

# Mock config
import yaml
with open("scoring/config/trust_signals.yml", "r") as f:
    config = yaml.safe_load(f)

# Mock detected attributes from user snapshot
detected_attrs = [
    DetectedAttribute(
        attribute_id="author_brand_identity_verified",
        label="Author/Brand Identity Verified",
        dimension="provenance",
        value=3.0,
        evidence="No attribution found",
        confidence=1.0
    ),
    DetectedAttribute(
        attribute_id="c2pa_cai_manifest_present",
        label="C2PA/CAI Manifest Present",
        dimension="provenance",
        value=1.0,
        evidence="No C2PA manifest found",
        confidence=1.0
    ),
    DetectedAttribute(
        attribute_id="domain_age",
        label="Domain Age",
        dimension="provenance",
        value=10.0,
        evidence="Domain age: 30.8 years",
        confidence=0.9
    ),
    DetectedAttribute(
        attribute_id="whois_privacy",
        label="WHOIS Privacy Status",
        dimension="provenance",
        value=7.8,
        evidence="Publicly visible",
        confidence=1.0
    )
]

def run_test():
    print("--- Starting Scoring Logic Reproduction ---")
    
    # 1. Map Attributes to Signals
    print("\n[Step 1] Mapping Attributes to Signals...")
    mapper = SignalMapper(config)
    mapped_signals = mapper.map_attributes_to_signals(detected_attrs)
    
    print(f"Mapped {len(mapped_signals)} signals:")
    for s in mapped_signals:
        print(f"  - {s.id} ({s.label}): Value={s.value:.2f}, Weight={s.weight}, Dimension={s.dimension}")

    # Check if we have the expected signals
    signal_ids = [s.id for s in mapped_signals]
    required = ["prov_author_bylines", "prov_metadata_c2pa", "prov_domain_trust"]
    for req in required:
        if req not in signal_ids:
            print(f"⚠️  WARNING: Signal '{req}' is missing from mapped output!")

    # 2. Add 'default' LLM signals that Scorer normally adds
    # We add dummy LLM signals to simulate real environment
    llm_signals = [
        SignalScore(
            id="prov_source_clarity",
            label="Source Attribution",
            dimension="Provenance",
            value=0.5, # Assume default/neutral from LLM if low? Or maybe 0.0?
            weight=0.20, # From config
            evidence=[],
            rationale="LLM analysis",
            confidence=1.0
        ),
        SignalScore(
            id="prov_date_freshness",
            label="Content Freshness",
            dimension="Provenance",
            value=0.5, # Assume default
            weight=0.20,
            evidence=[],
            rationale="Heuristic",
            confidence=1.0
        )
    ]
    
    # Note: Scorer uses hardcoded weights in the code I viewed?
    # lines 125: weight=0.25 for prov_source_clarity
    # This might be the issue! Scorer.py has hardcoded weights?
    
    combined_signals = mapped_signals + llm_signals

    # 3. Aggregate
    print("\n[Step 3] Aggregating Provenance Dimension...")
    aggregator = ScoringAggregator(config)
    
    dim_score = aggregator.aggregate_dimension("Provenance", combined_signals)
    
    print(f"\n🏆 Final Provenance Score: {dim_score.value:.2f} / 10.0")
    print(f"   Confidence: {dim_score.confidence:.2f}")
    print(f"   Signal Count: {len(dim_score.signals)}")


if __name__ == "__main__":
    run_test()
