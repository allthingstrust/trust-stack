"""Data models for the Trust Stack Rating Tool.

This module now exposes two sets of models:

* SQLAlchemy ORM models that back the new persistence layer
* Legacy dataclasses that maintain compatibility with existing ingestion
  and scoring modules during the refactor
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

# SQLAlchemy base for ORM models
Base = declarative_base()


class Brand(Base):
    """Brand being analyzed."""

    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    industry = Column(String, nullable=True)
    primary_domains = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    runs = relationship("Run", back_populates="brand", cascade="all, delete-orphan")


class Scenario(Base):
    """Analysis scope or playbook."""

    __tablename__ = "scenarios"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    runs = relationship("Run", back_populates="scenario", cascade="all, delete-orphan")


class Run(Base):
    """One execution of the pipeline for a given brand and scenario."""

    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, nullable=False)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    status = Column(String, default="pending", nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    config = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)

    brand = relationship("Brand", back_populates="runs")
    scenario = relationship("Scenario", back_populates="runs")
    assets = relationship("ContentAsset", back_populates="run", cascade="all, delete-orphan")
    summary = relationship("TrustStackSummary", back_populates="run", uselist=False, cascade="all, delete-orphan")


class ContentAsset(Base):
    """Represents one atomic asset that is scored."""

    __tablename__ = "content_assets"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    source_type = Column(String, nullable=False)
    channel = Column(String, nullable=True)
    url = Column(Text, nullable=True)
    external_id = Column(String, nullable=True)
    title = Column(Text, nullable=True)
    raw_content = Column(Text, nullable=True)
    normalized_content = Column(Text, nullable=True)
    modality = Column(String, default="text")
    language = Column(String, nullable=True)
    screenshot_path = Column(Text, nullable=True)  # Path to S3 screenshot
    visual_analysis = Column(JSON, default=dict)   # Full visual analysis result
    meta_info = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    run = relationship("Run", back_populates="assets")
    scores = relationship("DimensionScores", back_populates="asset", cascade="all, delete-orphan")


class DimensionScores(Base):
    """Per asset dimension scores."""

    __tablename__ = "dimension_scores"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("content_assets.id"), nullable=False)
    score_provenance = Column(Float, nullable=True)
    score_verification = Column(Float, nullable=True)
    score_transparency = Column(Float, nullable=True)
    score_coherence = Column(Float, nullable=True)
    score_resonance = Column(Float, nullable=True)
    score_ai_readiness = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    classification = Column(String, nullable=True)
    rationale = Column(JSON, default=dict)
    flags = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    asset = relationship("ContentAsset", back_populates="scores")


class TrustStackSummary(Base):
    """Aggregated metrics for a run."""

    __tablename__ = "truststack_summary"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False, unique=True)
    avg_provenance = Column(Float, nullable=True)
    avg_verification = Column(Float, nullable=True)
    avg_transparency = Column(Float, nullable=True)
    avg_coherence = Column(Float, nullable=True)
    avg_resonance = Column(Float, nullable=True)
    avg_ai_readiness = Column(Float, nullable=True)
    authenticity_ratio = Column(Float, nullable=True)
    overall_trust_stack_score = Column(Float, nullable=True)
    summary_insights = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    run = relationship("Run", back_populates="summary")


# ---------------------------------------------------------------------------
# Legacy dataclasses (kept for backward compatibility with existing pipeline)
# ---------------------------------------------------------------------------


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
    GOOD = "good"  # 60-79
    FAIR = "fair"  # 40-59
    POOR = "poor"  # 0-39


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

    # Visual Analysis fields
    screenshot_path: Optional[str] = None
    visual_analysis: Optional[Dict[str, Any]] = None

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
            self.score_provenance * weights.provenance
            + self.score_resonance * weights.resonance
            + self.score_coherence * weights.coherence
            + self.score_transparency * weights.transparency
            + self.score_verification * weights.verification
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
class EvidenceItem:
    """A single piece of evidence with contextual URL for Key Signal Evaluation.
    
    Enables the [ISSUE][EXAMPLE][URL] format in reports, providing:
    - description: The issue or finding (e.g., "Missing author byline")
    - example: Specific quote or observation from content (e.g., "No 'By' attribution found")
    - url: URL where this can be viewed in context
    """
    description: str  # The issue or finding
    example: str = ""  # Specific example from the content
    url: str = ""  # URL where this can be viewed


@dataclass
class DetectedAttribute:
    """Represents a Trust Stack attribute detected in content"""

    attribute_id: str
    dimension: str  # provenance, resonance, coherence, transparency, verification (5 dimensions)
    label: str
    value: float  # 1-10 rating from Trust Stack scoring rules
    evidence: str  # What triggered the detection (legacy string format)
    confidence: float = 1.0  # 0.0-1.0 confidence in detection
    suggestion: Optional[str] = None  # LLM-generated improvement suggestion (e.g., "Change 'X' → 'Y'")
    source_url: str = ""  # URL of the content where this attribute was detected
    # v5.1 Trust Signal Context
    status: str = "present"  # present, absent, partial, unknown
    reason: Optional[str] = None  # not_in_dom, unreadable, blocked, client_rendered


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
        import warnings

        warnings.warn(
            "AuthenticityRatio is deprecated. Use TrustStackRating for new implementations.",
            DeprecationWarning,
            stacklevel=2,
        )

    @property
    def extended_ar(self) -> float:
        """Extended AR formula: (A + 0.5S) ÷ (A + S + I) × 100"""
        if self.total_items == 0:
            return 0.0
        return (self.authentic_items + 0.5 * self.suspect_items) / self.total_items * 100

    @classmethod
    def from_ratings(
        cls, ratings: List[ContentScores], brand_id: str, source: str, run_id: str
    ) -> "AuthenticityRatio":
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
            authenticity_ratio_pct=ar_pct,
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
    classified_scores: Optional[List[Any]] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
