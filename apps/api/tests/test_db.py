from __future__ import annotations

import importlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, String, Table, inspect
from sqlalchemy.orm import Session

from app.core import config as config_module
from app.db import base as base_module
from app.db import session as session_module


@dataclass(frozen=True)
class _FakeSettings:
    """Mock de settings: DSN SQLite, sin PostgreSQL ni secretos."""

    DATABASE_URL: str


@pytest.fixture
def db_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    url = f"sqlite:///{tmp_path / 'talentos-test.db'}"
    monkeypatch.setattr(config_module, "get_settings", lambda: _FakeSettings(url))
    module = importlib.reload(session_module)
    yield module
    monkeypatch.undo()
    importlib.reload(session_module)


@pytest.fixture
def probe_table() -> Iterator[Table]:
    table = Table(
        "probe",
        base_module.Base.metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey("probe.id")),
        Column("code", String(20), unique=True),
        Column("kind", String(20)),
        Index(None, "kind"),
        CheckConstraint("id > 0", name="positive_id"),
    )
    yield table
    base_module.Base.metadata.remove(table)


def test_engine_uses_mocked_settings_url(db_module: ModuleType) -> None:
    assert str(db_module.engine.url).startswith("sqlite:///")
    assert getattr(db_module.engine.pool, "_pre_ping", None) is True
    with db_module.SessionLocal() as session:
        assert isinstance(session, Session)


def test_metadata_create_all_on_sqlite(db_module: ModuleType, probe_table: Table) -> None:
    base_module.Base.metadata.create_all(db_module.engine)

    assert inspect(db_module.engine).get_table_names() == [probe_table.name]

    base_module.Base.metadata.drop_all(db_module.engine)
    assert inspect(db_module.engine).get_table_names() == []


def test_naming_convention_covers_pk_fk_uk_ix_ck(probe_table: Table) -> None:
    convention = base_module.Base.metadata.naming_convention
    assert {"pk", "fk", "uq", "ix", "ck"} <= convention.keys()

    constraint_names = {item.name for item in probe_table.constraints}
    assert "pk_probe" in constraint_names
    assert "fk_probe_parent_id_probe" in constraint_names
    assert "uq_probe_code" in constraint_names
    assert "ck_probe_positive_id" in constraint_names
    assert any(
        index.name is not None and index.name.startswith("ix_") and "kind" in index.name
        for index in probe_table.indexes
    )


def test_get_db_closes_session(db_module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSession:
        closed = False

        def close(self) -> None:
            self.closed = True

    fake = FakeSession()
    monkeypatch.setattr(db_module, "SessionLocal", lambda: fake)

    generator = db_module.get_db()
    assert next(generator) is fake
    with pytest.raises(StopIteration):
        next(generator)

    assert fake.closed is True
