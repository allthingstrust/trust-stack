"""
Data models for Trust Stack Rating tool
Matching the AWS Athena schema structure
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import warnings

class ContentSource(Enum):
    REDDIT = "reddit"
    AMAZON = "amazon"
    YOUTUBE = "youtube"
    BRAVE = "brave"

class ContentClass(Enum):
    """Legacy classification - kept for backward compatibility"""
    AUTHENTIC = "authentic"
    SUSPECT = "suspect"
    INAUTHENTIC = "inauthentic"

class RatingBand(Enum):
    """Optional descriptive bands for ratings (not used for AR calculation)"""
    EXCELLENT = "excellent"  # 80-100
    GOOD = "good"           # 60-79
    FAIR = "fair"           # 40-59
    POOR = "poor"           # 0-39

@dataclass
class NormalizedContent:
    """Matches ar_content_normalized_v2 table schema with enhanced Trust Stack fields"""
    content_id: str
    src: str
    platform_id: str
    author: str
    title: str
    body: str
    rating: Optional[float] = None
    upvotes: Optional[int] = None
    helpful_count: Optional[float] = None
    event_ts: str = ""  # Stored as string for Athena compatibility
    run_id: str = ""
    meta: Dict[str, str] = None

    # Enhanced Trust Stack fields for 5D analysis
    url: str = ""  # Full URL of the content
    published_at: Optional[str] = None  # ISO datetime string
    modality: str = "text"  # text, image, video, audio
    channel: str = "unknown"  # youtube, reddit, amazon, instagram, etc.
    platform_type: str = "unknown"  # owned, social, marketplace, email

    # URL source classification for ratio enforcement
    source_type: str = "unknown"  # brand_owned, third_party, unknown
    source_tier: str = "unknown"  # specific tier within brand_owned or third_party
    
    # Language detection
    language: str = "en"  # Detected language code (e.g., 'en', 'fr', 'es')
    
    # Structure-aware text extraction for improved tone shift detection
    structured_body: Optional[List[Dict[str, str]]] = None  # HTML structure metadata
    # Format: [{"text": "...", "element_type": "h1", "semantic_role": "headline"}, ...]

    def __post_init__(self):
        if self.meta is None:
            self.meta = {}

@dataclass
class ContentScores:
    """
    Matches ar_content_scores_v2 table schema.
    Stores dimension scores (0.0-1.0 scale internally).
    For Trust Stack Ratings, use rating_* properties that expose 0-100 scale.
    """
    content_id: str
    brand: str
    src: str
    event_ts: str
    score_provenance: float
    score_resonance: float
    score_coherence: float
    score_transparency: float
    score_verification: float
    class_label: str = ""  # Legacy field - optional for backward compatibility
    is_authentic: bool = False  # Legacy field - optional
    rubric_version: str = "v2.0-trust-stack"
    run_id: str = ""
    meta: str = ""

    # Enhanced Trust Stack fields for 5D analysis
    modality: str = "text"  # text, image, video, audio
    channel: str = "unknown"  # youtube, reddit, amazon, instagram, etc.
    platform_type: str = "unknown"  # owned, social, marketplace, email

    # URL source classification for ratio enforcement
    source_type: str = "unknown"  # brand_owned, third_party, unknown
    source_tier: str = "unknown"  # specific tier within brand_owned or third_party

    @property
    def overall_score(self) -> float:
        """Calculate weighted overall score (0.0-1.0 scale)"""
        from config.settings import SETTINGS
        weights = SETTINGS['scoring_weights']

        return (
            self.score_provenance * weights.provenance +
            self.score_resonance * weights.resonance +
            self.score_coherence * weights.coherence +
            self.score_transparency * weights.transparency +
            self.score_verification * weights.verification
        )

    # Trust Stack Rating properties (0-100 scale)
    @property
    def rating_provenance(self) -> float:
        """Provenance rating on 0-100 scale"""
        return self.score_provenance * 100

    @property
    def rating_resonance(self) -> float:
        """Resonance rating on 0-100 scale"""
        return self.score_resonance * 100

    @property
    def rating_coherence(self) -> float:
        """Coherence rating on 0-100 scale"""
        return self.score_coherence * 100

    @property
    def rating_transparency(self) -> float:
        """Transparency rating on 0-100 scale"""
        return self.score_transparency * 100

    @property
    def rating_verification(self) -> float:
        """Verification rating on 0-100 scale"""
        return self.score_verification * 100

    @property
    def rating_comprehensive(self) -> float:
        """Comprehensive rating (weighted average) on 0-100 scale"""
        return self.overall_score * 100

    @property
    def rating_band(self) -> RatingBand:
        """Optional descriptive band based on comprehensive rating"""
        rating = self.rating_comprehensive
        if rating >= 80:
            return RatingBand.EXCELLENT
        elif rating >= 60:
            return RatingBand.GOOD
        elif rating >= 40:
            return RatingBand.FAIR
        else:
            return RatingBand.POOR

# Alias for clearer naming in Trust Stack context
ContentRatings = ContentScores

@dataclass
class DetectedAttribute:
    """Represents a Trust Stack attribute detected in content"""
    attribute_id: str
    dimension: str  # provenance, resonance, coherence, transparency, verification (5 dimensions)
    label: str
    value: float  # 1-10 rating from Trust Stack scoring rules
    evidence: str  # What triggered the detection
    confidence: float = 1.0  # 0.0-1.0 confidence in detection
    suggestion: Optional[str] = None  # LLM-generated improvement suggestion (e.g., "Change 'X' → 'Y'")

@dataclass
class TrustStackRating:
    """
    Trust Stack Rating for a single digital property.
    This is the new primary model replacing AuthenticityRatio aggregation.
    """
    # Digital property identification
    content_id: str
    digital_property_type: str  # reddit_post, amazon_review, youtube_video, etc.
    digital_property_url: str
    brand_id: str
    run_id: str

    # Dimension ratings (0-100 scale)
    rating_provenance: float
    rating_resonance: float
    rating_coherence: float
    rating_transparency: float
    rating_verification: float
    rating_comprehensive: float  # Weighted average

    # Attribute analysis
    attributes_detected: List[DetectedAttribute] = field(default_factory=list)
    attributes_missing: List[str] = field(default_factory=list)

    # Optional descriptive band (not used for AR)
    rating_band: Optional[RatingBand] = None

    # Metadata
    rubric_version: str = "v2.0-trust-stack"
    event_ts: str = ""

    def get_rating_band(self) -> RatingBand:
        """Get descriptive band based on comprehensive rating"""
        if self.rating_comprehensive >= 80:
            return RatingBand.EXCELLENT
        elif self.rating_comprehensive >= 60:
            return RatingBand.GOOD
        elif self.rating_comprehensive >= 40:
            return RatingBand.FAIR
        else:
            return RatingBand.POOR

    def get_attributes_by_dimension(self, dimension: str) -> List[DetectedAttribute]:
        """Get all detected attributes for a specific dimension"""
        return [attr for attr in self.attributes_detected if attr.dimension == dimension]

@dataclass
class AuthenticityRatio:
    """
    LEGACY: AR calculation result for backward compatibility.
    New implementations should use TrustStackRating instead.
    This can be synthesized from ContentRatings using rating thresholds.
    """
    brand_id: str
    source: str
    run_id: str
    total_items: int
    authentic_items: int
    suspect_items: int
    inauthentic_items: int
    authenticity_ratio_pct: float

    def __post_init__(self):
        warnings.warn(
            "AuthenticityRatio is deprecated. Use TrustStackRating for new implementations.",
            DeprecationWarning,
            stacklevel=2
        )

    @property
    def extended_ar(self) -> float:
        """Extended AR formula: (A + 0.5S) ÷ (A + S + I) × 100"""
        if self.total_items == 0:
            return 0.0
        return (self.authentic_items + 0.5 * self.suspect_items) / self.total_items * 100

    @classmethod
    def from_ratings(cls, ratings: List[ContentScores], brand_id: str, source: str, run_id: str) -> 'AuthenticityRatio':
        """
        Synthesize AR from ContentRatings using thresholds:
        - Authentic: rating_comprehensive >= 75
        - Suspect: 40 <= rating_comprehensive < 75
        - Inauthentic: rating_comprehensive < 40
        """
        authentic = sum(1 for r in ratings if r.rating_comprehensive >= 75)
        suspect = sum(1 for r in ratings if 40 <= r.rating_comprehensive < 75)
        inauthentic = sum(1 for r in ratings if r.rating_comprehensive < 40)
        total = len(ratings)

        ar_pct = (authentic / total * 100) if total > 0 else 0.0

        return cls(
            brand_id=brand_id,
            source=source,
            run_id=run_id,
            total_items=total,
            authentic_items=authentic,
            suspect_items=suspect,
            inauthentic_items=inauthentic,
            authenticity_ratio_pct=ar_pct
        )

@dataclass
class BrandConfig:
    """Brand-specific configuration"""
    brand_id: str
    name: str
    keywords: List[str]
    exclude_keywords: List[str]
    sources: List[ContentSource]
    custom_scoring_weights: Optional[Dict[str, float]] = None
    active: bool = True

@dataclass
class PipelineRun:
    """Track pipeline execution"""
    run_id: str
    brand_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str = "running"  # running, completed, failed
    items_processed: int = 0
    errors: List[str] = None
    # Optional: hold classified scores produced by the scoring pipeline so
    # callers (reports/telemetry) can consume the exact objects that were
    # uploaded to S3/Athena.
    classified_scores: Optional[List[Any]] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
