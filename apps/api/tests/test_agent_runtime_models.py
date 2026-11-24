from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, event, inspect, select
from sqlalchemy.orm import Session as DBSession

import app.identity.models  # noqa: F401
from app.agents.models import (
    AgentEventType,
    AgentRun,
    AgentRunStatus,
    AgentTenantMismatchError,
    ApprovalStatus,
    InvalidAgentTransitionError,
    UnsafeAgentPayloadError,
)
from app.agents.repositories import (
    create_agent_event,
    create_approval,
    get_agent_run,
    get_agent_run_by_idempotency_key,
    get_approval,
    get_or_create_agent_run,
    update_agent_run_status,
)
from app.agents.schemas import (
    AgentEventCreate,
    AgentRunStart,
    ApprovalDecision,
    workflow_state,
)
from app.db.base import Base
from app.identity.models import Organization, User

_AGENT_TABLES = {"agent_runs", "agent_events", "approvals", "agent_checkpoints"}


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")

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


def _seed(db: DBSession) -> tuple[Organization, Organization, User, User]:
    org_a = Organization(name="Org A", slug="agent-runtime-org-a")
    org_b = Organization(name="Org B", slug="agent-runtime-org-b")
    user_a = User(
        email="owner-a-agent@example.test", password_hash="synthetic-hash", name="Synthetic A"
    )
    user_b = User(
        email="owner-b-agent@example.test", password_hash="synthetic-hash", name="Synthetic B"
    )
    db.add_all([org_a, org_b, user_a, user_b])
    db.flush()
    return org_a, org_b, user_a, user_b


def _run(
    db: DBSession,
    org: Organization,
    user: User,
    *,
    key: str = "idem-synthetic-1",
    correlation: uuid.UUID | None = None,
) -> AgentRun:
    return get_or_create_agent_run(
        db,
        organization_id=org.id,
        workflow="matching",
        version="v1",
        idempotency_key=key,
        correlation_id=correlation or uuid.uuid4(),
        actor_id=user.id,
        input_ref="storage://synthetic/input",
    )


def test_agent_run_transitions_are_validated_not_free_strings(db: DBSession) -> None:
    org_a, _, user_a, _ = _seed(db)
    run = _run(db, org_a, user_a)

    update_agent_run_status(db, run, AgentRunStatus.RUNNING)
    update_agent_run_status(db, run, AgentRunStatus.WAITING_APPROVAL)
    update_agent_run_status(db, run, AgentRunStatus.RUNNING)
    update_agent_run_status(db, run, AgentRunStatus.COMPLETED)
    assert run.status is AgentRunStatus.COMPLETED

    invalid = _run(db, org_a, user_a, key="idem-invalid")
    with pytest.raises(InvalidAgentTransitionError):
        update_agent_run_status(db, invalid, AgentRunStatus.COMPLETED)
    with pytest.raises(InvalidAgentTransitionError):
        update_agent_run_status(db, run, AgentRunStatus.RUNNING)
    with pytest.raises(InvalidAgentTransitionError):
        invalid.transition_to(cast(AgentRunStatus, "done"))


def test_duplicate_idempotency_key_creates_one_run_per_tenant(db: DBSession) -> None:
    org_a, org_b, user_a, user_b = _seed(db)
    first = _run(db, org_a, user_a, key="same-key")
    second = _run(db, org_a, user_a, key="same-key")
    other_tenant = _run(db, org_b, user_b, key="same-key")

    assert first.id == second.id
    assert other_tenant.id != first.id
    existing = get_agent_run_by_idempotency_key(db, org_a.id, "same-key")
    assert existing is not None
    assert existing.id == first.id
    runs = (
        db.execute(select(type(first)).where(type(first).organization_id == org_a.id))
        .scalars()
        .all()
    )
    assert len(runs) == 1


def test_approval_records_actor_time_and_rejects_second_decision(db: DBSession) -> None:
    org_a, _, user_a, _ = _seed(db)
    run = _run(db, org_a, user_a, key="approval-run")
    approval = create_approval(
        db,
        organization_id=org_a.id,
        agent_run_id=run.id,
        action_type="create_message_draft",
        payload={"draft_id": "draft-synthetic"},
    )
    decided_at = datetime.now(UTC)
    approval.decide(ApprovalStatus.APPROVED, user_a.id, decided_at)
    db.flush()

    assert approval.status is ApprovalStatus.APPROVED
    assert approval.decided_by == user_a.id
    assert approval.decided_at == decided_at
    with pytest.raises(InvalidAgentTransitionError):
        approval.decide(ApprovalStatus.REJECTED, user_a.id, decided_at)


def test_cross_tenant_repositories_do_not_read_other_org(db: DBSession) -> None:
    org_a, org_b, user_a, _ = _seed(db)
    run_a = _run(db, org_a, user_a, key="tenant-run")
    approval_a = create_approval(
        db,
        organization_id=org_a.id,
        agent_run_id=run_a.id,
        action_type="request_human_approval",
        payload={"action": "draft"},
    )

    assert get_agent_run(db, org_b.id, run_a.id) is None
    assert get_approval(db, org_b.id, approval_a.id) is None
    with pytest.raises(AgentTenantMismatchError):
        create_agent_event(
            db,
            organization_id=org_b.id,
            agent_run_id=run_a.id,
            event_type=AgentEventType.RUN_STARTED,
            payload={"step": "start"},
            correlation_id=run_a.correlation_id,
        )


def test_event_payload_rejects_secrets_cv_and_chain_of_thought(db: DBSession) -> None:
    org_a, _, user_a, _ = _seed(db)
    run = _run(db, org_a, user_a, key="safe-payload")

    for unsafe in (
        {"api_key": "synthetic-value"},
        {"cv_text": "Synthetic resume"},
        {"chain_of_thought": "hidden"},
        {"note": "Bearer synthetic-token"},
    ):
        with pytest.raises(ValidationError):
            AgentEventCreate.model_validate(
                {
                    "agent_run_id": run.id,
                    "event_type": "run.started",
                    "correlation_id": run.correlation_id,
                    "payload": unsafe,
                }
            )
    with pytest.raises(UnsafeAgentPayloadError):
        create_agent_event(
            db,
            organization_id=org_a.id,
            agent_run_id=run.id,
            event_type=AgentEventType.RUN_STARTED,
            payload={"nested": {"secret": "synthetic"}},
            correlation_id=run.correlation_id,
        )

    event = create_agent_event(
        db,
        organization_id=org_a.id,
        agent_run_id=run.id,
        event_type=AgentEventType.RUN_STARTED,
        payload={"node": "job_analyst", "attempt": 1},
        correlation_id=run.correlation_id,
    )
    assert set(event.payload) == {"node", "attempt"}
    assert "synthetic-token" not in json.dumps(event.payload)


def test_start_contract_and_workflow_state_are_serializable(db: DBSession) -> None:
    org_a, _, user_a, _ = _seed(db)
    run = _run(db, org_a, user_a, key="state-run")
    start = AgentRunStart.model_validate(
        {
            "workflow": "matching",
            "version": "v1",
            "idempotency_key": "state-run",
            "correlation_id": str(run.correlation_id),
            "actor_id": str(user_a.id),
        }
    )
    assert start.workflow == "matching"
    with pytest.raises(ValidationError):
        AgentRunStart.model_validate(
            {
                "workflow": "matching",
                "version": "v1",
                "idempotency_key": "state-run",
                "correlation_id": str(run.correlation_id),
                "actor_id": str(user_a.id),
                "organization_id": str(org_a.id),
            }
        )
    with pytest.raises(ValidationError):
        ApprovalDecision.model_validate(
            {
                "approval_id": str(uuid.uuid4()),
                "decision": "pending",
                "decided_by": str(user_a.id),
            }
        )

    state = workflow_state(
        organization_id=org_a.id,
        actor_id=user_a.id,
        correlation_id=run.correlation_id,
        agent_run_id=run.id,
        idempotency_key="state-run",
    )
    restored = json.loads(json.dumps(state))
    assert restored["status"] == "pending"
    assert restored["errors"] == []
    assert restored["approvals"] == []
    assert "sqlalchemy" not in json.dumps(state).lower()


def test_agent_runtime_migration_upgrade_check_and_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "migration-agent-runtime.db"
    url = f"sqlite:///{db_file}"

    class _Settings:
        DATABASE_URL = url

    monkeypatch.setattr("app.core.config.get_settings", lambda: _Settings())
    monkeypatch.setattr("logging.config.fileConfig", lambda *_args, **_kwargs: None)
    api_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(api_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(api_root / "migrations"))

    command.upgrade(alembic_config, "0009_assessment")
    engine = create_engine(url)
    try:
        before = set(inspect(engine).get_table_names())
        assert not _AGENT_TABLES & before

        command.upgrade(alembic_config, "head")
        after = set(inspect(engine).get_table_names())
        assert _AGENT_TABLES <= after
        command.check(alembic_config)

        command.downgrade(alembic_config, "0009_assessment")
        reverted = set(inspect(engine).get_table_names())
        assert not _AGENT_TABLES & reverted
    finally:
        engine.dispose()
