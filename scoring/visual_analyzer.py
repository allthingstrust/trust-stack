"""
Visual Analyzer Module

Uses multimodal AI (Gemini) to analyze page screenshots for design quality,
dark patterns, and visual coherence, feeding results into Trust Stack scoring.
"""

import base64
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

logger = logging.getLogger('scoring.visual_analyzer')

# Optional Google Generative AI import
try:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig
    GOOGLE_AVAILABLE = True
except ImportError:
    genai = None
    GenerationConfig = None
    GOOGLE_AVAILABLE = False


@dataclass
class VisualSignal:
    """A single visual analysis signal."""
    signal_id: str
    label: str
    score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    evidence: str
    issues: List[str] = field(default_factory=list)


@dataclass
class VisualAnalysisResult:
    """Complete visual analysis result for a page."""
    url: str
    success: bool
    signals: Dict[str, VisualSignal] = field(default_factory=dict)
    dark_patterns: List[Dict[str, Any]] = field(default_factory=list)
    design_assessment: str = ""
    overall_visual_score: float = 0.0
    error: Optional[str] = None
    model: str = ""
    screenshot_s3_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "url": self.url,
            "success": self.success,
            "signals": {
                k: {
                    "signal_id": v.signal_id,
                    "label": v.label,
                    "score": v.score,
                    "confidence": v.confidence,
                    "evidence": v.evidence,
                    "issues": v.issues,
                }
                for k, v in self.signals.items()
            },
            "dark_patterns": self.dark_patterns,
            "design_assessment": self.design_assessment,
            "overall_visual_score": self.overall_visual_score,
            "error": self.error,
            "model": self.model,
            "screenshot_s3_key": self.screenshot_s3_key,
        }


# Visual analysis prompt template
VISUAL_ANALYSIS_PROMPT = """You are a UX/design expert analyzing a webpage screenshot. Evaluate the page across these dimensions and provide scores from 0.0 (worst) to 1.0 (best).

## Analysis Dimensions

1. **Design Quality (vis_design_quality)**
   - Professional typography, spacing, color harmony
   - Clear visual hierarchy and information architecture
   - Modern, polished aesthetic vs. dated/amateur appearance
   
2. **Dark Pattern Detection (vis_dark_patterns)**
   - Score HIGH (0.8-1.0) if NO dark patterns present
   - Score LOW (0.0-0.3) if dark patterns detected
   - Look for: fake urgency timers, hidden costs, misdirection, confirmshaming, roach motel patterns, bait & switch
   
3. **Visual Brand Coherence (vis_brand_coherence)**
   - Consistent logo placement, color palette, visual identity
   - Professional brand presentation
   - Coherent design language across visible elements

4. **Visual Accessibility (vis_accessibility)**
   - Good contrast ratios for text/background
   - Readable font sizes
   - Color-blind friendly design choices

5. **Visual Trust Indicators (vis_trust_indicators)**
   - Presence of trust badges, security seals, certifications
   - Professional contact information visible
   - SSL/secure indicators if applicable

6. **Visual Clutter (vis_clutter_score)**
   - Score HIGH (0.8-1.0) if clean, focused design
   - Score LOW (0.0-0.3) if cluttered with ads, popups, distractions
   - Evaluate ad density and distraction level

## Page Context
- URL: {url}
- Brand: {brand_name}

## Output Format

Respond with valid JSON only, no markdown formatting:

{{
  "signals": {{
    "vis_design_quality": {{
      "score": 0.0-1.0,
      "confidence": 0.0-1.0,
      "evidence": "Brief explanation",
      "issues": ["issue1", "issue2"]
    }},
    "vis_dark_patterns": {{
      "score": 0.0-1.0,
      "confidence": 0.0-1.0,
      "evidence": "Brief explanation",
      "issues": ["specific dark pattern found"]
    }},
    "vis_brand_coherence": {{
      "score": 0.0-1.0,
      "confidence": 0.0-1.0,
      "evidence": "Brief explanation",
      "issues": []
    }},
    "vis_accessibility": {{
      "score": 0.0-1.0,
      "confidence": 0.0-1.0,
      "evidence": "Brief explanation",
      "issues": []
    }},
    "vis_trust_indicators": {{
      "score": 0.0-1.0,
      "confidence": 0.0-1.0,
      "evidence": "Brief explanation",
      "issues": []
    }},
    "vis_clutter_score": {{
      "score": 0.0-1.0,
      "confidence": 0.0-1.0,
      "evidence": "Brief explanation",
      "issues": []
    }}
  }},
  "dark_patterns_detected": [
    {{
      "type": "urgency|scarcity|misdirection|confirmshaming|roach_motel|bait_switch|hidden_costs|other",
      "severity": "low|medium|high",
      "description": "What was detected"
    }}
  ],
  "design_assessment": "2-3 sentence overall design assessment",
  "overall_visual_score": 0.0-1.0
}}
"""

# Signal labels for display
SIGNAL_LABELS = {
    "vis_design_quality": "Design Quality",
    "vis_dark_patterns": "Dark Pattern Absence",
    "vis_brand_coherence": "Visual Brand Coherence",
    "vis_accessibility": "Visual Accessibility",
    "vis_trust_indicators": "Visual Trust Indicators",
    "vis_clutter_score": "Visual Clutter (Low is Bad)",
}


class VisualAnalyzer:
    """Analyzes page screenshots for design quality and trust signals."""

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        api_key: Optional[str] = None,
    ):
        """
        Initialize the visual analyzer.

        Args:
            model: Gemini model to use for analysis
            api_key: Google API key (falls back to GOOGLE_API_KEY env var)
        """
        self.model = model or os.getenv("VISUAL_ANALYSIS_MODEL", "gemini-2.0-flash")
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self._initialized = False

    def _ensure_initialized(self):
        """Initialize Gemini API if not already done."""
        if self._initialized:
            return

        if not GOOGLE_AVAILABLE:
            raise ImportError(
                "google-generativeai package not installed. "
                "Run: pip install google-generativeai"
            )

        if not self.api_key:
            raise ValueError(
                "Google API key not configured. "
                "Set GOOGLE_API_KEY environment variable."
            )

        genai.configure(api_key=self.api_key)
        self._initialized = True

    def analyze(
        self,
        screenshot_bytes: bytes,
        url: str,
        brand_context: Optional[Dict[str, Any]] = None,
        mime_type: str = "image/png",
    ) -> VisualAnalysisResult:
        """
        Analyze a page screenshot for visual trust signals.

        Args:
            screenshot_bytes: Image data
            url: URL of the page
            brand_context: Optional brand configuration
            mime_type: MIME type of the image (image/png or image/jpeg)

        Returns:
            VisualAnalysisResult with all signal scores
        """
        if not screenshot_bytes:
            return VisualAnalysisResult(
                url=url,
                success=False,
                error="No screenshot data provided",
            )

        try:
            self._ensure_initialized()
        except (ImportError, ValueError) as e:
            return VisualAnalysisResult(
                url=url,
                success=False,
                error=str(e),
            )

        brand_name = "Unknown Brand"
        if brand_context:
            brand_name = brand_context.get("brand_name", brand_context.get("brand_id", "Unknown Brand"))

        # Build the prompt
        prompt = VISUAL_ANALYSIS_PROMPT.format(
            url=url,
            brand_name=brand_name,
        )

        try:
            # Create the Gemini model
            gemini_model = genai.GenerativeModel(self.model)

            # Prepare the image for the API
            image_part = {
                "mime_type": mime_type,
                "data": screenshot_bytes,
            }

            # Send multimodal request
            config = GenerationConfig(
                max_output_tokens=2048,
                temperature=0.2,  # Lower temperature for more consistent analysis
            )

            response = gemini_model.generate_content(
                [prompt, image_part],
                generation_config=config,
            )

            response_text = response.text
            
            # Record cost
            try:
                from scoring.cost_tracker import cost_tracker
                usage = response.usage_metadata
                if usage:
                    cost_tracker.record_cost(
                        model=self.model,
                        input_tokens=usage.prompt_token_count,
                        output_tokens=usage.candidates_token_count
                    )
                else:
                    # Fallback if no usage metadata
                    # Estimate based on image + prompt chars
                    # Image is approx 258 tokens (standard) + text
                    est_input = 258 + len(prompt) // 4
                    est_output = len(response_text) // 4
                    cost_tracker.record_cost(self.model, est_input, est_output)
            except Exception as e:
                logger.warning(f"Failed to record visual analysis cost: {e}")
            
            # --- USER REQUEST: Log full visual analysis feedback to terminal ---
            logger.info("="*60)
            logger.info(f"🎨 VISUAL ANALYSIS FEEDBACK FOR: {url}")
            logger.info("-" * 60)
            logger.info(response_text)
            logger.info("="*60)
            # -------------------------------------------------------------------

            # Parse the response
            return self._parse_response(response_text, url)

        except Exception as e:
            logger.error("Visual analysis failed for %s: %s", url, e)
            return VisualAnalysisResult(
                url=url,
                success=False,
                error=str(e),
                model=self.model,
            )

    def _parse_response(self, response_text: str, url: str) -> VisualAnalysisResult:
        """Parse Gemini response into VisualAnalysisResult."""
        try:
            # Clean up response - remove markdown code blocks if present
            cleaned = response_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)

            # Build signals
            signals = {}
            raw_signals = data.get("signals", {})
            for signal_id, signal_data in raw_signals.items():
                signals[signal_id] = VisualSignal(
                    signal_id=signal_id,
                    label=SIGNAL_LABELS.get(signal_id, signal_id),
                    score=float(signal_data.get("score", 0.5)),
                    confidence=float(signal_data.get("confidence", 0.7)),
                    evidence=signal_data.get("evidence", ""),
                    issues=signal_data.get("issues", []),
                )

            return VisualAnalysisResult(
                url=url,
                success=True,
                signals=signals,
                dark_patterns=data.get("dark_patterns_detected", []),
                design_assessment=data.get("design_assessment", ""),
                overall_visual_score=float(data.get("overall_visual_score", 0.5)),
                model=self.model,
            )

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse visual analysis JSON: %s", e)
            logger.debug("Raw response: %s", response_text[:500])
            return VisualAnalysisResult(
                url=url,
                success=False,
                error=f"Failed to parse AI response: {e}",
                model=self.model,
            )

    def analyze_batch(
        self,
        screenshots: List[Dict[str, Any]],
        brand_context: Optional[Dict[str, Any]] = None,
    ) -> List[VisualAnalysisResult]:
        """
        Analyze multiple screenshots.

        Args:
            screenshots: List of dicts with 'screenshot_bytes' and 'url' keys
            brand_context: Optional brand configuration

        Returns:
            List of VisualAnalysisResult objects
        """
        results = []
        for item in screenshots:
            result = self.analyze(
                screenshot_bytes=item.get("screenshot_bytes", b""),
                url=item.get("url", ""),
                brand_context=brand_context,
            )
            results.append(result)
        return results


# Singleton instance
_VISUAL_ANALYZER: Optional[VisualAnalyzer] = None


def get_visual_analyzer() -> VisualAnalyzer:
    """Get the global visual analyzer instance."""
    global _VISUAL_ANALYZER
    if _VISUAL_ANALYZER is None:
        _VISUAL_ANALYZER = VisualAnalyzer(
            model=os.getenv("VISUAL_ANALYSIS_MODEL", "gemini-2.0-flash"),
        )
    return _VISUAL_ANALYZER
