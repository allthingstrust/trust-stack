"""
Scoring Aggregator (v5.1)
Responsible for combining individual signal scores into dimension scores
and the overall trust score, applying weights, visibility multipliers, 
coverage penalties, and knockout caps.
"""

import logging
from typing import List, Dict, Any, Tuple
from scoring.types import SignalScore, DimensionScore, TrustScore

logger = logging.getLogger(__name__)


# v5.1: Visibility-based weight multipliers
# Based on (Discoverability_Signal, Visibility_Signal) tuple
VISIBILITY_MULTIPLIERS = {
    ("machine_visible", "user_visible_high"): 1.0,
    ("machine_visible", "user_visible_low"): 0.9,
    ("machine_visible", "backend_only"): 0.8,
    ("not_machine_visible", "user_visible_high"): 0.8,
    ("not_machine_visible", "user_visible_low"): 0.6,
    ("not_machine_visible", "backend_only"): 0.5,
}

# v5.1: Updated dimension weights
DIMENSION_WEIGHTS = {
    "provenance": 0.25,
    "resonance": 0.15,
    "coherence": 0.20,
    "transparency": 0.15,
    "verification": 0.25,
}


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

    def _signal_defs_for_dimension(self, dimension_name: str) -> Dict[str, Dict[str, Any]]:
        """Get all signal definitions for a given dimension."""
        dim = dimension_name.lower()
        return {
            sid: sdef for sid, sdef in self.signals_config.items()
            if str(sdef.get('dimension', '')).lower() == dim
        }

    def _get_visibility_multiplier(self, signal_def: Dict[str, Any]) -> float:
        """
        v5.1: Calculate visibility-based weight multiplier.
        
        Args:
            signal_def: Signal definition from config
            
        Returns:
            Multiplier between 0.5 and 1.0
        """
        discoverability = signal_def.get('discoverability_signal', 'machine_visible')
        visibility = signal_def.get('visibility_signal', 'user_visible_high')
        return VISIBILITY_MULTIPLIERS.get((discoverability, visibility), 0.8)

    def _calculate_effective_weight(self, signal: SignalScore, signal_def: Dict[str, Any]) -> float:
        """
        v5.1: Calculate effective weight = dimension_weight * visibility_multiplier
        
        Args:
            signal: The signal score
            signal_def: Signal definition from config
            
        Returns:
            Effective weight for aggregation
        """
        base_weight = signal.weight
        multiplier = self._get_visibility_multiplier(signal_def)
        return base_weight * multiplier

    def _calculate_coverage_cap(self, coverage_ratio: float) -> float:
        """
        v5.1: Calculate coverage penalty cap.
        
        Args:
            coverage_ratio: Ratio of covered required signals (0.0-1.0)
            
        Returns:
            Maximum allowed score based on coverage
        """
        if coverage_ratio < 0.5:
            return 6.0
        elif coverage_ratio < 0.8:
            return 8.0
        else:
            return 10.0

    def _determine_confidence_level(self, coverage_ratio: float, knockout_triggered: bool) -> str:
        """
        v5.1: Determine confidence level string.
        
        Args:
            coverage_ratio: Ratio of covered required signals
            knockout_triggered: Whether any knockout signal failed
            
        Returns:
            "high", "medium", or "low"
        """
        if coverage_ratio >= 0.8 and not knockout_triggered:
            return "high"
        elif coverage_ratio >= 0.5:
            return "medium"
        else:
            return "low"

    def aggregate_dimension(self, dimension_name: str, signals: List[SignalScore]) -> DimensionScore:
        """
        Aggregate a list of signal scores into a single dimension score.
        
        v5.1 Formula:
        1. Raw score = weighted average using effective_weight (base * visibility_multiplier)
        2. Apply coverage_cap based on % of required signals covered
        3. Apply knockout_cap if any knockout signal fails (score <= 3)
        4. Apply core_deficit_cap if any required signal is low (score <= 3)
        5. Final score = min(raw, coverage_cap, knockout_cap, core_deficit_cap)
        """
        if not signals:
            logger.warning(f"No signals provided for dimension {dimension_name}")
            return DimensionScore(
                name=dimension_name, 
                value=0.0, 
                confidence=0.0, 
                coverage=0.0,
                signals=[],
                weight=DIMENSION_WEIGHTS.get(dimension_name.lower(), 0.2)
            )

        # Filter signals for this dimension
        dimension_signals = [s for s in signals if s.dimension.lower() == dimension_name.lower()]
        logger.info(f"DEBUG: Aggregating {dimension_name} with {len(dimension_signals)} signals: {[s.id for s in dimension_signals]}")
        
        # Get signal definitions for this dimension
        defs = self._signal_defs_for_dimension(dimension_name)
        
        total_weighted_score = 0.0
        total_weight = 0.0
        total_confidence = 0.0
        
        # Build lookup of best value per signal ID (for knockout checking)
        by_id_best: Dict[str, float] = {}
        for s in dimension_signals:
            status = getattr(s, 'status', 'known')
            if status == 'unknown':
                # Treat unknown signals as passing (value=1.0) for knockout/presence checks
                # This prevents "unknown" from triggering penalties like core deficit
                by_id_best[s.id] = 1.0
            else:
                by_id_best[s.id] = max(by_id_best.get(s.id, 0.0), float(s.value))
        
        present_signal_ids = set(by_id_best.keys())
        
        # Calculate weighted score with visibility multipliers
        for signal in dimension_signals:
            status = getattr(signal, 'status', 'known')
            if status == 'unknown':
                logger.debug(f"Signal '{signal.id}' status is unknown, excluding from weighted score calculation")
                continue
                
            signal_def = defs.get(signal.id, {})
            effective_weight = self._calculate_effective_weight(signal, signal_def)
            
            # SignalScore.value is normalized 0.0-1.0
            # Auto-normalize fallback: if value looks like 1-10 scale, convert it
            if signal.value > 1.0 and signal.value <= 10.0:
                logger.warning(
                    f"Signal '{signal.id}' has value {signal.value} which appears to be "
                    f"on 1-10 scale. Auto-normalizing to 0.0-1.0 by dividing by 10."
                )
                signal_value = signal.value / 10.0
            elif signal.value < 0.0 or signal.value > 10.0:
                logger.warning(
                    f"Signal '{signal.id}' has out-of-range value {signal.value} "
                    f"(expected 0.0-1.0). Clamping to valid range."
                )
                signal_value = max(0.0, min(1.0, signal.value))
            else:
                signal_value = signal.value
                
            total_weighted_score += signal_value * effective_weight
            total_weight += effective_weight
            total_confidence += signal.confidence * effective_weight

        # Calculate raw score (0-10 scale)
        if total_weight > 0:
            raw_score = (total_weighted_score / total_weight) * 10.0
            normalized_confidence = total_confidence / total_weight
        else:
            raw_score = 0.0
            normalized_confidence = 0.0

        # v5.1: Coverage penalty calculation
        # Only count signals marked as required
        required_signal_ids = [
            sid for sid, sdef in defs.items()
            if str(sdef.get('requirement_level', '')).lower() in ('core', 'required')
            or sdef.get('required_bool') is True
        ]
        
        if required_signal_ids:
            covered_required = present_signal_ids.intersection(set(required_signal_ids))
            coverage_ratio = len(covered_required) / len(required_signal_ids)
        else:
            coverage_ratio = 1.0
            
        coverage_cap = self._calculate_coverage_cap(coverage_ratio)
        logger.info(f"DEBUG: Coverage for {dimension_name}: {coverage_ratio:.2f} -> cap={coverage_cap}")

        # v5.1: Knockout and core deficit caps
        dimension_cap = 10.0
        knockout_triggered = False
        core_deficit = False
        
        # Get knockout signals for this dimension
        knockout_signal_ids = [
            sid for sid, sdef in defs.items()
            if sdef.get('knockout_flag') is True or sdef.get('knockout_bool') is True
        ]
        
        # Check for knockout failures (score <= 3 on 1-10 scale, or <= 0.3 on 0-1 scale)
        knockout_threshold = 0.3  # 3/10 normalized
        for sid in knockout_signal_ids:
            if sid in present_signal_ids:
                signal_value = by_id_best.get(sid, 0.0)
                if signal_value <= knockout_threshold:
                    logger.info(f"DEBUG: Knockout signal '{sid}' below threshold ({signal_value} <= {knockout_threshold})")
                    dimension_cap = min(dimension_cap, 4.0)
                    knockout_triggered = True
                    break
                    
        # Check for core deficit (required signal with score <= 3)
        core_deficit_threshold = 0.3
        for sid in required_signal_ids:
            if sid in present_signal_ids:
                signal_value = by_id_best.get(sid, 0.0)
                if signal_value <= core_deficit_threshold:
                    logger.info(f"DEBUG: Core signal '{sid}' deficit ({signal_value} <= {core_deficit_threshold})")
                    dimension_cap = min(dimension_cap, 6.0)
                    core_deficit = True
                    break

        # Also cap if required signals are missing entirely
        missing_core = [sid for sid in required_signal_ids if sid not in present_signal_ids]
        if missing_core:
            logger.info(f"DEBUG: Missing core signals for {dimension_name}: {missing_core}. Applying core cap.")
            dimension_cap = min(dimension_cap, 6.0)
            core_deficit = True

        # v5.1: Final score = min(raw, coverage_cap, dimension_cap)
        final_score = min(raw_score, coverage_cap, dimension_cap)
        final_score = max(0.0, min(10.0, final_score))
        
        # v5.1: Confidence level
        confidence_level = self._determine_confidence_level(coverage_ratio, knockout_triggered)
        
        # Blend confidence with coverage (keeping numeric value for compatibility)
        normalized_confidence = (normalized_confidence * 0.5) + (coverage_ratio * 0.5)
        
        logger.info(
            f"DEBUG: {dimension_name} score: raw={raw_score:.1f}, "
            f"coverage_cap={coverage_cap}, dim_cap={dimension_cap}, "
            f"final={final_score:.1f}, confidence={confidence_level}"
        )
        
        return DimensionScore(
            name=dimension_name,
            value=final_score,
            confidence=normalized_confidence,
            coverage=coverage_ratio,
            signals=dimension_signals,
            weight=DIMENSION_WEIGHTS.get(dimension_name.lower(), 0.2)
        )

    def calculate_trust_score(self, dimension_scores: List[DimensionScore], metadata: Dict[str, Any] = None) -> TrustScore:
        """
        Calculate the overall Trust Score from dimension scores.
        
        v5.1 Formula:
        - Use updated dimension weights (Provenance/Verification: 0.25, Coherence: 0.20, Resonance/Transparency: 0.15)
        - Normalize weights for dimensions that are present
        - Trust Score = weighted average * 10 (Result is 0-100)
        """
        total_score = 0.0
        total_weight = 0.0
        total_confidence = 0.0
        total_coverage = 0.0
        
        dimensions_map = {}
        
        for dim in dimension_scores:
            dimensions_map[dim.name.lower()] = dim
            
            # Use v5.1 dimension weights
            weight = DIMENSION_WEIGHTS.get(dim.name.lower(), 0.2)
            
            # Skip dimensions with no score (N/A)
            if dim.value <= 0.0 and dim.coverage <= 0.0:
                continue
                
            total_score += dim.value * weight
            total_weight += weight
            total_confidence += dim.confidence * weight
            total_coverage += dim.coverage * weight

        if total_weight > 0:
            # Normalize weights for present dimensions
            final_score = (total_score / total_weight) * 10.0  # Scale 0-10 -> 0-100
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
