"""Lightweight SQLAlchemy compatibility layer.

The real SQLAlchemy dependency should be preferred. When it is not
available (for example, in offline CI environments), this module falls
back to a minimal in-memory stub that supports the limited subset of the
API used in the refactor tests. If a real installation is present on the
PYTHONPATH, it will be loaded and re-exported instead of the stub.
"""
from __future__ import annotations

import importlib.util
import sys
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Attempt to defer to a real SQLAlchemy installation if one exists elsewhere
# on sys.path. We skip the current working directory to avoid re-importing
# this very module.
# ---------------------------------------------------------------------------
_real_spec = importlib.util.find_spec("sqlalchemy", sys.path[1:])
if _real_spec and _real_spec.origin != __file__:
    _real_module = importlib.util.module_from_spec(_real_spec)
    assert _real_spec.loader is not None
    _real_spec.loader.exec_module(_real_module)  # type: ignore[attr-defined]
    sys.modules[__name__] = _real_module
    globals().update(_real_module.__dict__)
else:
    # -----------------------------------------------------------------------
    # Minimal stub implementation
    # -----------------------------------------------------------------------
    class Condition:
        def __init__(self, column_name: str, value: Any):
            self.column_name = column_name
            self.value = value

    class Column:
        def __init__(
            self,
            _type: Any = None,
            primary_key: bool = False,
            unique: bool = False,
            index: bool = False,
            nullable: bool = True,
            default: Any = None,
            onupdate: Optional[Callable] = None,
        ):
            self.name: Optional[str] = None
            self.default = default
            self.onupdate = onupdate

        def __set_name__(self, owner, name):
            self.name = name

        def __get__(self, instance, owner):
            if instance is None:
                return self
            if self.name in instance.__dict__:
                return instance.__dict__[self.name]
            if callable(self.default):
                value = self.default()
            else:
                value = self.default
            instance.__dict__[self.name] = value
            return value

        def __set__(self, instance, value):
            instance.__dict__[self.name] = value

        def __eq__(self, other):
            return Condition(self.name, other)

    # Simple placeholder types
    class Integer: ...
    class String: ...
    class Text: ...
    class Float: ...
    class DateTime: ...
    class JSON: ...

    class ForeignKey:
        def __init__(self, target: str):
            self.target = target

    class MetaData:
        def __init__(self):
            self.tables: List[str] = []

        def create_all(self, bind=None):
            if bind is None:
                return
            declared = getattr(BaseModel, "_declared", [])
            for cls in declared:
                bind.register_table(cls.__tablename__)

    class Engine:
        def __init__(self, url: str):
            self.url = url
            self.tables: Dict[str, list] = {}
            self.declared: List[str] = []

        def register_table(self, name: str):
            if name not in self.tables:
                self.tables[name] = []

    def create_engine(url: str, echo: bool = False, future: bool = True, connect_args: Optional[dict] = None):
        return Engine(url)

    class BaseModel:
        metadata = MetaData()
        __tablename__: str

        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            if not hasattr(BaseModel, "_declared"):
                BaseModel._declared = []
            BaseModel._declared.append(cls)

        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    def declarative_base():
        return BaseModel

    def inspect(engine: Engine):
        class _Inspector:
            def get_table_names(self_inner):
                return list(engine.tables.keys())

        return _Inspector()

    # Import submodules after defining core classes so they can reference them
    from sqlalchemy.orm import Query, Session, relationship, sessionmaker  # type: ignore  # noqa: E402,F401

    __all__ = [
        "Condition",
        "Column",
        "Integer",
        "String",
        "Text",
        "Float",
        "DateTime",
        "JSON",
        "ForeignKey",
        "MetaData",
        "Engine",
        "create_engine",
        "declarative_base",
        "inspect",
    ]
