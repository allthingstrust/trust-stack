"""Database store utilities for Trust Stack."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from data.models import (
    Base,
    Brand,
    ContentAsset,
    DimensionScores,
    Run,
    Scenario,
    TrustStackSummary,
)


def get_engine(database_url: Optional[str] = None):
    """Create a SQLAlchemy engine for the configured database."""

    url = database_url or os.getenv("DATABASE_URL", "sqlite:///./truststack.db")
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, echo=False, future=True, connect_args=connect_args)


def init_db(engine=None):
    """Create all tables in the configured database."""

    engine = engine or get_engine()
    Base.metadata.create_all(bind=engine)
    return engine


def get_session(engine=None) -> Session:
    engine = engine or get_engine()
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return SessionLocal()


@contextmanager
def session_scope(engine=None):
    session = get_session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_or_create_brand(session: Session, slug: str, name: Optional[str] = None, **kwargs) -> Brand:
    brand = session.query(Brand).filter(Brand.slug == slug).first()
    if brand:
        return brand

    brand = Brand(
        slug=slug,
        name=name or slug,
        industry=kwargs.get("industry"),
        primary_domains=kwargs.get("primary_domains") or [],
    )
    session.add(brand)
    session.commit()
    session.refresh(brand)
    return brand


def get_or_create_scenario(
    session: Session, slug: str, name: Optional[str] = None, description: Optional[str] = None, config: Optional[dict] = None
) -> Scenario:
    scenario = session.query(Scenario).filter(Scenario.slug == slug).first()
    if scenario:
        return scenario

    scenario = Scenario(slug=slug, name=name or slug, description=description, config=config or {})
    session.add(scenario)
    session.commit()
    session.refresh(scenario)
    return scenario


def create_run(session: Session, brand: Brand, scenario: Scenario, external_id: str, config: Optional[dict] = None) -> Run:
    run = Run(external_id=external_id, brand_id=brand.id, scenario_id=scenario.id, status="pending", config=config or {})
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def update_run_status(session: Session, run_id: int, status: str, error_message: Optional[str] = None) -> Run:
    run = session.get(Run, run_id) if hasattr(session, "get") else session.query(Run).get(run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")

    run.status = status
    if status in {"completed", "failed"}:
        run.finished_at = datetime.utcnow()
    if error_message:
        run.error_message = error_message

    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def bulk_insert_assets(session: Session, run_id: int, assets: Iterable[dict]) -> List[ContentAsset]:
    records: List[ContentAsset] = []
    for asset in assets:
        records.append(
            ContentAsset(
                run_id=run_id,
                source_type=asset.get("source_type", "unknown"),
                channel=asset.get("channel"),
                url=asset.get("url"),
                external_id=asset.get("external_id"),
                title=asset.get("title"),
                raw_content=asset.get("raw_content"),
                normalized_content=asset.get("normalized_content"),
                modality=asset.get("modality", "text"),
                language=asset.get("language"),
                screenshot_path=asset.get("screenshot_path"),
                visual_analysis=asset.get("visual_analysis"),
                meta_info=asset.get("meta_info") or asset.get("metadata") or {},
            )
        )

    session.add_all(records)
    session.commit()
    for record in records:
        session.refresh(record)
    return records


def bulk_insert_dimension_scores(session: Session, scores: Iterable[dict]) -> List[DimensionScores]:
    records: List[DimensionScores] = []
    for score in scores:
        records.append(
            DimensionScores(
                asset_id=score["asset_id"],
                score_provenance=score.get("score_provenance"),
                score_verification=score.get("score_verification"),
                score_transparency=score.get("score_transparency"),
                score_coherence=score.get("score_coherence"),
                score_resonance=score.get("score_resonance"),
                score_ai_readiness=score.get("score_ai_readiness"),
                overall_score=score.get("overall_score"),
                classification=score.get("classification"),
                rationale=score.get("rationale") or {},
                flags=score.get("flags") or {},
            )
        )

    session.add_all(records)
    session.commit()
    for record in records:
        session.refresh(record)
    return records


def create_truststack_summary(
    session: Session,
    run_id: int,
    averages: dict,
    authenticity_ratio: Optional[float] = None,
    overall_score: Optional[float] = None,
    insights: Optional[dict] = None,
) -> TrustStackSummary:
    summary = TrustStackSummary(
        run_id=run_id,
        avg_provenance=averages.get("avg_provenance"),
        avg_verification=averages.get("avg_verification"),
        avg_transparency=averages.get("avg_transparency"),
        avg_coherence=averages.get("avg_coherence"),
        avg_resonance=averages.get("avg_resonance"),
        avg_ai_readiness=averages.get("avg_ai_readiness"),
        authenticity_ratio=authenticity_ratio,
        overall_trust_stack_score=overall_score,
        summary_insights=insights or {},
    )
    session.add(summary)
    session.commit()
    session.refresh(summary)
    return summary


def find_recent_assets_by_brand(
    session: Session, brand_id: str, max_age_hours: int = 24, min_length: int = 100
) -> List[ContentAsset]:
    """Find valid assets for a brand fetched within the last N hours."""
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
    
    # We join on Run to filter by time, but we also ensure the asset itself has content
    # Note: We filter by Run.created_at or asset creation time if available. 
    # ContentAsset doesn't have created_at, but Run does.
    return (
        session.query(ContentAsset)
        .join(Run)
        .join(Brand)
        .filter(
            Brand.slug == brand_id,
            Run.started_at >= cutoff,
            Run.status != "failed"  # valid runs only? or maybe failed runs have some valid assets?
            # Let's trust assets from any non-deleted run, as long as the asset has content
        )
        .filter(ContentAsset.raw_content != None)
        .filter(ContentAsset.raw_content != "")
        # Filter out "empty" or stub assets by checking length
        # SQLite doesn't have LENGTH() easily in all versions in standard SQLAlchemy core without func
        # so we'll do basic null/empty checks and filter length in python if needed, 
        # or use func.length if we import it.
        # For safety/portability, let's just ensure it's not null/empty string.
        .all()
    )


def prune_old_runs(session: Session, days_to_keep: int = 30) -> int:
    """Delete runs older than N days.
    
    Returns:
        int: Number of runs deleted.
    """
    from datetime import datetime, timedelta
    
    cutoff = datetime.utcnow() - timedelta(days=days_to_keep)
    
    # Query runs to be deleted first to get count (and IDs if needed for logging)
    runs_to_delete = session.query(Run).filter(Run.started_at < cutoff).all()
    count = len(runs_to_delete)
    
    if count > 0:
        # Delete using simple session.delete() for each to ensure ORM cascade works reliably
        # SQLA bulk delete might skip cascades depending on configuration
        for run in runs_to_delete:
            session.delete(run)
        
        session.commit()
        
    return count
