
# We need to simulate the Scorer's behavior with the new weights
import sys
import os
import yaml

sys.path.append(os.getcwd())
from scoring.aggregator import ScoringAggregator
from scoring.signal_mapper import SignalMapper
from scoring.types import SignalScore
from data.models import DetectedAttribute

# Load actual config
with open("scoring/config/trust_signals.yml", "r") as f:
    config = yaml.safe_load(f)

# Mock attributes
detected_attrs = [
    DetectedAttribute("author_brand_identity_verified", "Author", "provenance", 3.0, "None", 1.0),
    DetectedAttribute("c2pa_cai_manifest_present", "C2PA", "provenance", 1.0, "None", 1.0),
    DetectedAttribute("domain_age", "Domain Age", "provenance", 10.0, "Old", 1.0),
    DetectedAttribute("whois_privacy", "WHOIS", "provenance", 7.8, "Visible", 1.0)
]

print("--- Running Post-Fix Verification ---")
# 1. Map
mapper = SignalMapper(config)
mapped_signals = mapper.map_attributes_to_signals(detected_attrs)

# 2. Add LLM Signals with CORRECTED weights (0.2 instead of 0.25)
# This simulates what Scorer.py does now
llm_signals = [
    SignalScore(
        id="prov_source_clarity",
        label="Source Attribution",
        dimension="Provenance",
        value=0.5, # Assume default is 0.5 (from Scorer logic? No, from LLM. If LLM fails/low, maybe 0.5?)
        # Let's assume neutral 5/10 for now.
        weight=config['signals']['prov_source_clarity']['weight'], 
        evidence=[], rationale="LLM", confidence=1.0
    ),
    SignalScore(
        id="prov_date_freshness",
        label="Content Freshness",
        dimension="Provenance",
        value=0.5, # Assume default 5/10
        weight=config['signals']['prov_date_freshness']['weight'],
        evidence=[], rationale="Heuristic", confidence=1.0
    )
]

combined = mapped_signals + llm_signals

# 3. Aggregate
agg = ScoringAggregator(config)
score = agg.aggregate_dimension("Provenance", combined)

print(f"Final Score: {score.value:.2f}")

# Check Expectation
# Signals: 
# Author (0.3), C2PA (0.1), Domain (1.0), Whois (0.78), Clarity (0.5), Freshness (0.5)
# Weights: all 0.20
# Sum of values: 0.3 + 0.1 + 1.0 + 0.78 + 0.5 + 0.5 = 3.18
# Weighted Sum: 3.18 * 0.2 = 0.636
# Total Weight: 1.2
# Result: 0.636 / 1.2 = 0.53 -> 5.30

# What if Clarity/Freshness are 0?
# Sum = 0.3 + 0.1 + 1.0 + 0.78 = 2.18
# Weighted Sum = 2.18 * 0.2 = 0.436
# Total Weight = 1.2
# Result = 0.436 / 1.2 = 0.363 -> 3.63

print("Expected w/ neutral LLM: ~5.3")
print("Expected w/ zero LLM: ~3.6")

