from datetime import datetime

from data import export_s3, store
from data.models import Brand, ContentAsset, DimensionScores, Run, Scenario


class _FakeS3:
    def __init__(self):
        self.keys = []

    def put_object(self, Bucket, Key, Body, ContentType=None):  # noqa: N802
        self.keys.append(Key)


def test_export_run_to_s3(monkeypatch, tmp_path):
    fake = _FakeS3()
    monkeypatch.setattr(export_s3.boto3, "client", lambda *_args, **_kwargs: fake)

    engine = store.get_engine(f"sqlite:///{tmp_path/'export.db'}")
    store.init_db(engine)

    with store.session_scope(engine) as session:
        brand = Brand(slug="demo", name="Demo")
        scenario = Scenario(slug="web", name="Web")
        session.add_all([brand, scenario])
        session.commit()
        run = Run(external_id="demo_run", brand_id=brand.id, scenario_id=scenario.id, started_at=datetime.utcnow())
        session.add(run)
        session.commit()
        session.refresh(run)

        asset = ContentAsset(run_id=run.id, source_type="synthetic", normalized_content="hello world")
        session.add(asset)
        session.commit()
        session.refresh(asset)

        score = DimensionScores(asset_id=asset.id, score_provenance=0.5, overall_score=0.5)
        session.add(score)
        session.commit()

    raw_keys, analytics_keys = export_s3.export_run_to_s3(engine, run.id, bucket="demo-bucket")

    assert raw_keys  # raw asset uploaded
    assert analytics_keys  # parquet tables uploaded
    assert len(fake.keys) == len(raw_keys) + len(analytics_keys)
