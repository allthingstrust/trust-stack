"""
Scoring Aggregator
Responsible for combining individual signal scores into dimension scores
and the overall trust score, applying weights and normalization.
"""

import logging
from typing import List, Dict, Any
from scoring.types import SignalScore, DimensionScore, TrustScore

logger = logging.getLogger(__name__)

class ScoringAggregator:
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize aggregator with trust signals configuration
        
        Args:
            config: Loaded trust_signals.yml configuration
        """
        self.config = config
        self.dimensions_config = config.get('dimensions', {})
        self.signals_config = config.get('signals', {})

    def aggregate_dimension(self, dimension_name: str, signals: List[SignalScore]) -> DimensionScore:
        """
        Aggregate a list of signal scores into a single dimension score.
        
        Formula:
        Dimension Score = Sum(Signal Value * Signal Weight) / Sum(Signal Weights) * 10
        """
        if not signals:
            logger.warning(f"No signals provided for dimension {dimension_name}")
            return DimensionScore(name=dimension_name, value=0.0, confidence=0.0, signals=[])

        total_weighted_score = 0.0
        total_weight = 0.0
        total_confidence = 0.0
        
        for signal in signals:
            # Ensure signal belongs to this dimension
            if signal.dimension.lower() != dimension_name.lower():
                continue
                
            weight = signal.weight
            total_weighted_score += signal.value * weight
            total_weight += weight
            total_confidence += signal.confidence * weight # Weighted confidence

        # Normalize
        if total_weight > 0:
            normalized_score = (total_weighted_score / total_weight) * 10.0 # Scale to 0-10
            normalized_confidence = total_confidence / total_weight
            
            # Penalize confidence for missing signals if defined in config
            # (Simple heuristic: if we have fewer signals than expected, reduce confidence)
            expected_signals = len([s for s in self.signals_config.values() if s.get('dimension') == dimension_name])
            if expected_signals > 0:
                coverage_ratio = len(signals) / expected_signals
                # Blend signal confidence with coverage ratio (50/50)
                normalized_confidence = (normalized_confidence * 0.5) + (coverage_ratio * 0.5)
        else:
            normalized_score = 0.0
            normalized_confidence = 0.0

        # Clamp
        normalized_score = max(0.0, min(10.0, normalized_score))
        
        return DimensionScore(
            name=dimension_name,
            value=normalized_score,
            confidence=normalized_confidence,
            signals=signals,
            weight=self.dimensions_config.get(dimension_name, {}).get('weight', 0.2)
        )

    def calculate_trust_score(self, dimension_scores: List[DimensionScore], metadata: Dict[str, Any] = None) -> TrustScore:
        """
        Calculate the overall Trust Score from dimension scores.
        
        Formula:
        Trust Score = Sum(Dimension Value * Dimension Weight) * 10
        (Result is 0-100)
        """
        total_score = 0.0
        total_weight = 0.0
        total_confidence = 0.0
        
        dimensions_map = {}
        
        for dim in dimension_scores:
            dimensions_map[dim.name.lower()] = dim
            weight = dim.weight
            
            # Dimension value is 0-10, we want final score 0-100
            # So we multiply by 10 at the end
            total_score += dim.value * weight
            total_weight += weight
            total_confidence += dim.confidence * weight

        if total_weight > 0:
            final_score = (total_score / total_weight) * 10.0 # Scale 0-10 -> 0-100
            final_confidence = total_confidence / total_weight
        else:
            final_score = 0.0
            final_confidence = 0.0
            
        return TrustScore(
            overall=final_score,
            confidence=final_confidence,
            dimensions=dimensions_map,
            metadata=metadata or {}
        )
