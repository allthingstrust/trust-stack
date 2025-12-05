import pytest
from scoring.types import TrustScore, DimensionScore, SignalScore
from scoring.aggregator import ScoringAggregator

# Golden Data Fixtures
GOLDEN_SIGNALS = {
    "high_trust_brand": [
        SignalScore(id="prov_author_bylines", label="Bylines", dimension="Provenance", value=1.0, weight=0.25, evidence=[], rationale="", confidence=1.0),
        SignalScore(id="prov_metadata_c2pa", label="C2PA", dimension="Provenance", value=0.8, weight=0.25, evidence=[], rationale="", confidence=0.9),
        SignalScore(id="res_engagement", label="Engagement", dimension="Resonance", value=0.9, weight=0.3, evidence=[], rationale="", confidence=0.8),
    ],
    "low_trust_brand": [
        SignalScore(id="prov_author_bylines", label="Bylines", dimension="Provenance", value=0.0, weight=0.25, evidence=[], rationale="", confidence=1.0),
        SignalScore(id="prov_metadata_c2pa", label="C2PA", dimension="Provenance", value=0.0, weight=0.25, evidence=[], rationale="", confidence=1.0),
    ]
}

MOCK_CONFIG = {
    "dimensions": {
        "Provenance": {"weight": 0.2},
        "Resonance": {"weight": 0.2}
    },
    "signals": {
        "prov_author_bylines": {"dimension": "Provenance"},
        "prov_metadata_c2pa": {"dimension": "Provenance"},
        "res_engagement": {"dimension": "Resonance"}
    }
}

def test_aggregator_high_trust():
    aggregator = ScoringAggregator(MOCK_CONFIG)
    signals = GOLDEN_SIGNALS["high_trust_brand"]
    
    # Test Dimension Aggregation
    prov_score = aggregator.aggregate_dimension("Provenance", signals)
    assert prov_score.value > 8.0 # Should be high
    assert prov_score.confidence > 0.8
    
    # Test Trust Score Aggregation
    trust_score = aggregator.calculate_trust_score([prov_score])
    assert trust_score.overall > 80.0

def test_aggregator_low_trust():
    aggregator = ScoringAggregator(MOCK_CONFIG)
    signals = GOLDEN_SIGNALS["low_trust_brand"]
    
    prov_score = aggregator.aggregate_dimension("Provenance", signals)
    assert prov_score.value < 2.0 # Should be low
    
def test_missing_signals_penalty():
    # Test that missing signals reduce confidence
    aggregator = ScoringAggregator(MOCK_CONFIG)
    # Only 1 signal provided, but 2 expected for Provenance in MOCK_CONFIG (implied by test setup, though mock config logic in aggregator is simple)
    signals = [GOLDEN_SIGNALS["high_trust_brand"][0]] 
    
    prov_score = aggregator.aggregate_dimension("Provenance", signals)
    # Confidence should be lower than 1.0 because we only provided 1 signal
    # Note: The mock config in this test file doesn't fully populate 'signals' dict for the aggregator's expected_signals logic
    # unless we pass it in __init__.
    assert prov_score.confidence < 1.0
