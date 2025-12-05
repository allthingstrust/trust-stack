from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

@dataclass
class SignalScore:
    """Score for a single specific signal (e.g., 'prov_metadata_c2pa')"""
    id: str              # e.g. "prov_metadata_c2pa"
    label: str           # human-readable label
    dimension: str       # "Provenance", "Resonance", etc.
    value: float         # Normalized 0.0-1.0 score
    weight: float        # Relative importance within dimension (0.0-1.0)
    evidence: List[str]  # URLs, selectors, snippets, prompt IDs
    rationale: str       # Short explanation (LLM or heuristic)
    confidence: float    # 0.0-1.0 confidence in this specific signal
    source: str = "heuristic" # "heuristic", "llm", "external_api"

@dataclass
class DimensionScore:
    """Aggregated score for a dimension"""
    name: str            # "Provenance"
    value: float         # 0.0-10.0 score (to match existing 0-100 scale when multiplied by 10)
    confidence: float    # 0.0-1.0 confidence
    signals: List[SignalScore]
    weight: float = 0.2  # Default weight in overall score

@dataclass
class TrustScore:
    """Top-level trust score object"""
    overall: float       # 0.0-100.0 score
    confidence: float    # 0.0-1.0 confidence
    dimensions: Dict[str, DimensionScore]
    metadata: Dict[str, Any] = field(default_factory=dict) # brand, date, content coverage, model version
