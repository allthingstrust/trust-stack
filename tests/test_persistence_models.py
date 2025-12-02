from sqlalchemy import inspect

from data import store
from data.models import Base


def test_tables_created(tmp_path):
    db_url = f"sqlite:///{tmp_path/'test.db'}"
    engine = store.get_engine(db_url)
    store.init_db(engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "brands",
        "scenarios",
        "runs",
        "content_assets",
        "dimension_scores",
        "truststack_summary",
    }
    assert expected.issubset(tables)

