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

        # Filter signals for this dimension
        dimension_signals = [s for s in signals if s.dimension.lower() == dimension_name.lower()]
        logger.info(f"DEBUG: Aggregating {dimension_name} with {len(dimension_signals)} signals: {[s.id for s in dimension_signals]}")
        
        total_weighted_score = 0.0
        total_weight = 0.0
        total_confidence = 0.0
        
        for signal in dimension_signals:
            weight = signal.weight
            total_weighted_score += signal.value * weight
            total_weight += weight
            total_confidence += signal.confidence * weight # Weighted confidence

        # Normalize
        if total_weight > 0:
            normalized_score = (total_weighted_score / total_weight) * 10.0 # Scale to 0-10
            normalized_confidence = total_confidence / total_weight
            
            # Calculate coverage
            expected_signals = len([s for s in self.signals_config.values() if s.get('dimension') == dimension_name])
            coverage_ratio = 1.0
            if expected_signals > 0:
                # Count unique signal IDs present vs expected
                present_signal_ids = {s.id for s in dimension_signals}
                # Note: signals list might contain multiple instances if we allow duplicates, so set is safer
                coverage_ratio = min(1.0, len(present_signal_ids) / expected_signals)
                logger.info(f"DEBUG: Coverage for {dimension_name}: {coverage_ratio} ({len(present_signal_ids)}/{expected_signals}). Present: {present_signal_ids}")
                
                # Blend signal confidence with coverage ratio (50/50)
                normalized_confidence = (normalized_confidence * 0.5) + (coverage_ratio * 0.5)
        else:
            normalized_score = 0.0
            normalized_confidence = 0.0
            coverage_ratio = 0.0

        # Clamp
        normalized_score = max(0.0, min(10.0, normalized_score))
        logger.info(f"DEBUG: Final score for {dimension_name}: {normalized_score} (Conf: {normalized_confidence})")
        
        return DimensionScore(
            name=dimension_name,
            value=normalized_score,
            confidence=normalized_confidence,
            coverage=coverage_ratio,
            signals=dimension_signals,
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
        total_coverage = 0.0
        
        dimensions_map = {}
        
        for dim in dimension_scores:
            dimensions_map[dim.name.lower()] = dim
            weight = dim.weight
            
            # Dimension value is 0-10, we want final score 0-100
            # So we multiply by 10 at the end
            total_score += dim.value * weight
            total_weight += weight
            total_confidence += dim.confidence * weight
            total_coverage += dim.coverage * weight

        if total_weight > 0:
            final_score = (total_score / total_weight) * 10.0 # Scale 0-10 -> 0-100
            final_confidence = total_confidence / total_weight
            final_coverage = total_coverage / total_weight
        else:
            final_score = 0.0
            final_confidence = 0.0
            final_coverage = 0.0
            
        return TrustScore(
            overall=final_score,
            confidence=final_confidence,
            coverage=final_coverage,
            dimensions=dimensions_map,
            metadata=metadata or {}
        )
