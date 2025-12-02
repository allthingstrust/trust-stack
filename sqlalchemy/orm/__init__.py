from typing import Any, Iterable, List

from sqlalchemy import Condition


def relationship(*args, **kwargs):  # pragma: no cover - placeholder
    return None


class Query:
    def __init__(self, engine, model, data: List[Any]):
        self.engine = engine
        self.model = model
        self._data = list(data)

    def filter(self, condition: Condition):
        filtered = [obj for obj in self._data if getattr(obj, condition.column_name, None) == condition.value]
        return Query(self.engine, self.model, filtered)

    def filter_by(self, **kwargs):
        filtered = [obj for obj in self._data if all(getattr(obj, k, None) == v for k, v in kwargs.items())]
        return Query(self.engine, self.model, filtered)

    def first(self):
        return self._data[0] if self._data else None

    def all(self):
        return list(self._data)

    def count(self):
        return len(self._data)

    def get(self, key):
        for obj in self._data:
            if getattr(obj, "id", None) == key:
                return obj
        return None


class Session:
    def __init__(self, engine):
        self.engine = engine
        if not hasattr(engine, "tables"):
            engine.tables = {}

    def add(self, obj):
        table = self.engine.tables.setdefault(obj.__tablename__, [])
        if getattr(obj, "id", None) is None:
            obj.id = len(table) + 1
        # mimic onupdate
        for name, value in list(obj.__dict__.items()):
            attr = getattr(type(obj), name, None)
            if hasattr(attr, "onupdate") and attr.onupdate:
                obj.__dict__[name] = attr.onupdate()
        table.append(obj)

    def add_all(self, objs: Iterable[Any]):
        for obj in objs:
            self.add(obj)

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None

    def query(self, model):
        data = self.engine.tables.get(model.__tablename__, [])
        return Query(self.engine, model, data)

    def refresh(self, obj):
        return None

    def flush(self):
        return None

    def get(self, model, key):
        data = self.engine.tables.get(model.__tablename__, [])
        for obj in data:
            if getattr(obj, "id", None) == key:
                return obj
        return None


def sessionmaker(bind=None, autocommit=False, autoflush=False):
    def factory():
        return Session(bind)

    return factory

__all__ = ["relationship", "Query", "Session", "sessionmaker"]
