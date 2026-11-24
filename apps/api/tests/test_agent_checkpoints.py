from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import cast

import pytest
from langgraph.checkpoint.base import Checkpoint
from langgraph.types import RunnableConfig
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.identity.models  # noqa: F401
from app.agents.checkpoints import SQLAgentCheckpointSaver
from app.agents.models import (
    AgentCheckpoint,
    AgentRun,
    AgentTenantMismatchError,
    UnsafeAgentPayloadError,
    is_safe_payload_value,
    thread_id_for,
)
from app.agents.repositories import get_checkpoint, get_or_create_agent_run
from app.db.base import Base
from app.identity.models import Organization, User


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[DBSession]:
    with DBSession(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def saver(engine: Engine) -> SQLAgentCheckpointSaver:
    return SQLAgentCheckpointSaver(lambda: DBSession(engine, expire_on_commit=False))


def _seed(db: DBSession) -> tuple[Organization, Organization, User, User]:
    org_a = Organization(name="Org A", slug="checkpoint-org-a")
    org_b = Organization(name="Org B", slug="checkpoint-org-b")
    user_a = User(
        email="owner-a-checkpoint@example.test", password_hash="synthetic-hash", name="Synthetic A"
    )
    user_b = User(
        email="owner-b-checkpoint@example.test", password_hash="synthetic-hash", name="Synthetic B"
    )
    db.add_all([org_a, org_b, user_a, user_b])
    db.flush()
    return org_a, org_b, user_a, user_b


def _run(db: DBSession, org: Organization, user: User, key: str) -> AgentRun:
    return get_or_create_agent_run(
        db,
        organization_id=org.id,
        workflow="matching",
        version="v1",
        idempotency_key=key,
        correlation_id=uuid.uuid4(),
        actor_id=user.id,
    )


def _config(
    organization_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    *,
    checkpoint_id: str | None = None,
    tenant_claim: uuid.UUID | None = None,
) -> RunnableConfig:
    configurable: dict[str, object] = {
        "organization_id": str(tenant_claim or organization_id),
        "agent_run_id": str(agent_run_id),
        "thread_id": thread_id_for(organization_id, agent_run_id),
        "checkpoint_ns": "",
    }
    if checkpoint_id is not None:
        configurable["checkpoint_id"] = checkpoint_id
    return cast(RunnableConfig, {"configurable": configurable})


def _checkpoint(checkpoint_id: str, values: dict[str, object], version: int = 1) -> Checkpoint:
    return Checkpoint(
        v=version,
        id=checkpoint_id,
        ts="2026-11-24T00:00:00+00:00",
        channel_values=values,
        channel_versions={key: 1 for key in values},
        versions_seen={},
        updated_channels=list(values),
    )


def test_checkpoint_round_trip_preserves_thread_and_version(
    db: DBSession, saver: SQLAgentCheckpointSaver
) -> None:
    org_a, _, user_a, _ = _seed(db)
    run = _run(db, org_a, user_a, "checkpoint-round-trip")
    config = _config(org_a.id, run.id)
    values = {"status": "running", "attempt": 1}

    saved = saver.put(
        config, _checkpoint("cp-1", values), {"source": "input", "step": -1}, {"status": 1}
    )
    assert saved["configurable"]["checkpoint_id"] == "cp-1"

    loaded = saver.get_tuple(config)
    assert loaded is not None
    assert loaded.checkpoint["id"] == "cp-1"
    assert loaded.checkpoint["v"] == 1
    assert loaded.checkpoint["channel_values"] == values
    assert loaded.metadata["source"] == "input"
    assert loaded.pending_writes == []

    saver.put(
        config,
        _checkpoint("cp-2", {"status": "completed", "attempt": 2}, version=2),
        {"source": "loop", "step": 0},
        {"status": 2},
    )
    latest = saver.get_tuple(config)
    assert latest is not None
    assert latest.checkpoint["id"] == "cp-2"
    assert latest.checkpoint["v"] == 2
    first = saver.get_tuple(_config(org_a.id, run.id, checkpoint_id="cp-1"))
    assert first is not None
    assert first.checkpoint["channel_values"] == values
    assert len(list(saver.list(config))) == 2

    rows = db.execute(select(AgentCheckpoint)).scalars().all()
    assert len(rows) == 2
    assert all(row.thread_id == thread_id_for(org_a.id, run.id) for row in rows)
    assert all(is_safe_payload_value(row.payload) for row in rows)


def test_pending_writes_are_persisted_and_ordered(
    db: DBSession, saver: SQLAgentCheckpointSaver
) -> None:
    org_a, _, user_a, _ = _seed(db)
    run = _run(db, org_a, user_a, "checkpoint-writes")
    config = _config(org_a.id, run.id, checkpoint_id="cp-writes")
    saver.put_writes(
        config,
        [("status", "waiting_approval"), ("node", "quality_auditor")],
        "task-1",
        "node:quality",
    )
    saver.put(
        _config(org_a.id, run.id),
        _checkpoint("cp-writes", {"status": "waiting_approval"}),
        {"source": "loop", "step": 0},
        {"status": 1},
    )

    loaded = saver.get_tuple(config)
    assert loaded is not None
    assert loaded.pending_writes == [
        ("task-1", "status", "waiting_approval"),
        ("task-1", "node", "quality_auditor"),
    ]


def test_checkpoint_rejects_foreign_tenant_and_thread(
    db: DBSession, saver: SQLAgentCheckpointSaver
) -> None:
    org_a, org_b, user_a, _ = _seed(db)
    run_a = _run(db, org_a, user_a, "checkpoint-tenant")
    config = _config(org_a.id, run_a.id)
    saver.put(config, _checkpoint("cp-tenant", {"status": "running"}), {}, {})

    bad_claim = _config(org_a.id, run_a.id, tenant_claim=org_b.id)
    with pytest.raises(AgentTenantMismatchError):
        saver.put(bad_claim, _checkpoint("cp-bad", {"status": "running"}), {}, {})
    with pytest.raises(AgentTenantMismatchError):
        saver.get_tuple(bad_claim)

    foreign_thread = _config(org_b.id, run_a.id)
    with pytest.raises(AgentTenantMismatchError):
        saver.get_tuple(foreign_thread)

    assert get_checkpoint(db, org_b.id, thread_id_for(org_a.id, run_a.id), "", "cp-tenant") is None
    with pytest.raises(AgentTenantMismatchError):
        saver.delete_thread(thread_id_for(org_b.id, run_a.id))


def test_checkpoint_serialization_rejects_secrets_and_non_json_objects(
    db: DBSession, saver: SQLAgentCheckpointSaver
) -> None:
    org_a, _, user_a, _ = _seed(db)
    run = _run(db, org_a, user_a, "checkpoint-safe")
    # El saver abre su propia sesión sobre el mismo pool: confirmar la semilla
    # evita que un rollback de validación reverta las filas del fixture.
    db.commit()
    config = _config(org_a.id, run.id)

    with pytest.raises(UnsafeAgentPayloadError):
        saver.put(
            config,
            _checkpoint("cp-secret", {"payload": {"api_key": "synthetic-token"}}),
            {},
            {},
        )
    with pytest.raises(UnsafeAgentPayloadError):
        saver.put(config, _checkpoint("cp-object", {"client": object()}), {}, {})

    saver.put(config, _checkpoint("cp-safe", {"node": "job_analyst"}), {}, {})
    row = get_checkpoint(db, org_a.id, thread_id_for(org_a.id, run.id), "", "cp-safe")
    assert row is not None
    assert is_safe_payload_value(row.payload)
    assert "api_key" not in json.dumps(row.payload)


def test_delete_thread_only_removes_own_tenant_rows(
    db: DBSession, saver: SQLAgentCheckpointSaver
) -> None:
    org_a, org_b, user_a, user_b = _seed(db)
    run_a = _run(db, org_a, user_a, "delete-a")
    run_b = _run(db, org_b, user_b, "delete-b")
    saver.put(_config(org_a.id, run_a.id), _checkpoint("cp-a", {"status": "running"}), {}, {})
    saver.put(_config(org_b.id, run_b.id), _checkpoint("cp-b", {"status": "running"}), {}, {})

    saver.delete_thread(thread_id_for(org_a.id, run_a.id))

    assert get_checkpoint(db, org_a.id, thread_id_for(org_a.id, run_a.id), "", "cp-a") is None
    assert get_checkpoint(db, org_b.id, thread_id_for(org_b.id, run_b.id), "", "cp-b") is not None
