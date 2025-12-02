from core.run_manager import RunManager
from data import store
from data.models import ContentAsset, DimensionScores, Run, TrustStackSummary


class DummyScoringPipeline:
    def score_assets(self, assets, run_config):
        for asset in assets:
            yield {
                "asset_id": asset.id,
                "score_provenance": 0.8,
                "score_verification": 0.8,
                "score_transparency": 0.8,
                "score_coherence": 0.8,
                "score_resonance": 0.8,
                "score_ai_readiness": 0.8,
                "overall_score": 0.8,
                "classification": "Excellent",
            }


def test_run_manager_creates_entities(tmp_path):
    db_url = f"sqlite:///{tmp_path/'run.db'}"
    engine = store.get_engine(db_url)
    store.init_db(engine)

    manager = RunManager(engine=engine, scoring_pipeline=DummyScoringPipeline())
    run = manager.run_analysis(
        brand_slug="example_brand",
        scenario_slug="web",
        run_config={
            "assets": [
                {
                    "source_type": "synthetic",
                    "title": "Hello",
                    "normalized_content": "sample content",
                }
            ]
        },
    )

    with store.session_scope(engine) as session:
        refreshed_run = session.query(Run).get(run.id)
        assert refreshed_run.status == "completed"
        assert session.query(ContentAsset).filter_by(run_id=run.id).count() == 1
        assert session.query(DimensionScores).count() == 1
        summary = session.query(TrustStackSummary).filter_by(run_id=run.id).first()
        assert summary is not None
        assert summary.overall_trust_stack_score == 0.8


def test_run_manager_collects_serper(monkeypatch, tmp_path):
    engine = store.get_engine(f"sqlite:///{tmp_path/'serper.db'}")
    store.init_db(engine)

    manager = RunManager(engine=engine)

    captured = {}

    def fake_collect_serper(keywords, limit):
        captured["called"] = True
        return [
            {
                "source_type": "serper",
                "title": "Example",
                "normalized_content": "example content",
            }
        ]

    monkeypatch.setattr(manager, "_collect_from_serper", fake_collect_serper)

    assets = manager._collect_assets({"sources": ["serper"], "keywords": ["test"], "limit": 1})

    assert captured.get("called") is True
    assert len(assets) == 1
    assert assets[0]["source_type"] == "serper"

