from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

import app.candidates.models  # noqa: F401
import app.identity.models  # noqa: F401
from app.agents.models import UnsafeAgentPayloadError
from app.automation.models import (
    Automation,
    AutomationActionType,
    AutomationApproval,
    AutomationApprovalStatus,
    AutomationDomainError,
    AutomationRun,
    AutomationRunEvent,
    AutomationRunEventType,
    AutomationRunMode,
    AutomationRunStatus,
    AutomationStatus,
    AutomationTenantMismatchError,
    AutomationTriggerEventType,
    AutomationVersion,
    AutomationVersionImmutableError,
    InvalidAutomationTransitionError,
)
from app.automation.repositories import (
    create_approval,
    create_run,
    create_run_event,
    create_version,
    decide_approval,
    get_approval,
    get_automation,
    get_run_by_key,
    get_version,
    list_approvals_for_run,
    list_automations,
    list_run_events,
    list_runs,
    next_version,
    update_run_status,
)
from app.automation.schemas import (
    AutomationAction,
    AutomationApprovalDecision,
    AutomationCondition,
    AutomationRunCreate,
    AutomationRunEventCreate,
    AutomationTrigger,
    AutomationVersionCreate,
)
from app.db.base import Base
from app.identity.models import Organization, User

_AUTOMATION_TABLES = {
    "automations",
    "automation_versions",
    "automation_runs",
    "automation_run_events",
    "automation_approvals",
}
_FORBIDDEN_FIELDS = frozenset(
    {
        "age",
        "ethnicity",
        "gender",
        "health",
        "hire_decision",
        "hiring_decision",
        "nationality",
        "personality",
        "ranking",
        "rating",
        "religion",
        "score",
    }
)
_SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|password|secret|sk-[a-z0-9]{8,}|@)")


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


def _seed(db: DBSession) -> tuple[Organization, Organization, User, User, Automation, Automation]:
    org_a = Organization(name="Org A", slug="automation-org-a")
    org_b = Organization(name="Org B", slug="automation-org-b")
    user_a = User(
        email="owner-a-automation@example.test",
        password_hash="synthetic-hash",
        name="Synthetic A",
    )
    user_b = User(
        email="owner-b-automation@example.test",
        password_hash="synthetic-hash",
        name="Synthetic B",
    )
    db.add_all([org_a, org_b, user_a, user_b])
    db.flush()
    automation_a = Automation(
        organization_id=org_a.id, name="Synthetic rule A", created_by=user_a.id
    )
    automation_b = Automation(
        organization_id=org_b.id, name="Synthetic rule B", created_by=user_b.id
    )
    db.add_all([automation_a, automation_b])
    db.flush()
    return org_a, org_b, user_a, user_b, automation_a, automation_b


def _version(
    db: DBSession,
    org: Organization,
    automation: Automation,
    user: User,
    version: int = 1,
) -> AutomationVersion:
    return create_version(
        db,
        organization_id=org.id,
        automation_id=automation.id,
        version=version,
        trigger={"event_type": "application.stage_changed"},
        conditions=[{"field": "to_stage", "operator": "eq", "value": "interview"}],
        actions=[{"type": "record_note", "payload": {"note": "Synthetic reminder"}}],
        created_by=user.id,
    )


def _run(
    db: DBSession,
    org: Organization,
    automation: Automation,
    user: User,
    *,
    key: str = "idem-synthetic-1",
) -> AutomationRun:
    return create_run(
        db,
        organization_id=org.id,
        automation_id=automation.id,
        version=1,
        mode=AutomationRunMode.TEST,
        trigger_event_type=AutomationTriggerEventType.APPLICATION_STAGE_CHANGED,
        trigger_event_id=uuid.uuid4(),
        idempotency_key=key,
        correlation_id=uuid.uuid4(),
        actor_id=user.id,
    )


def _approval(
    db: DBSession,
    org: Organization,
    run: AutomationRun,
    user: User,
    *,
    action_type: AutomationActionType = AutomationActionType.CREATE_MESSAGE_DRAFT,
) -> AutomationApproval:
    return create_approval(
        db,
        organization_id=org.id,
        run_id=run.id,
        action_type=action_type,
        payload={"template_id": "interview-scheduling", "note": "Synthetic draft"},
        created_by=user.id,
    )


def test_automation_transitions_are_closed_and_archived_is_terminal() -> None:
    rule = Automation(
        name="rule",
        created_by=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        status=AutomationStatus.DRAFT,
    )
    assert rule.status is AutomationStatus.DRAFT

    rule.transition_to(AutomationStatus.ACTIVE)
    rule.transition_to(AutomationStatus.INACTIVE)
    rule.transition_to(AutomationStatus.ACTIVE)
    rule.transition_to(AutomationStatus.ARCHIVED)
    assert rule.status is AutomationStatus.ARCHIVED

    with pytest.raises(InvalidAutomationTransitionError):
        rule.transition_to(AutomationStatus.ACTIVE)
    with pytest.raises(InvalidAutomationTransitionError):
        Automation(
            name="draft", created_by=uuid.uuid4(), organization_id=uuid.uuid4()
        ).transition_to(AutomationStatus.INACTIVE)
    with pytest.raises(AutomationDomainError):
        rule.transition_to(cast(AutomationStatus, "enabled"))


def test_run_transitions_validate_pending_approval_and_terminals(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    run = _run(db, org_a, automation_a, user_a)

    update_run_status(db, org_a.id, run, AutomationRunStatus.RUNNING)
    update_run_status(db, org_a.id, run, AutomationRunStatus.WAITING_APPROVAL)
    update_run_status(db, org_a.id, run, AutomationRunStatus.RUNNING)
    update_run_status(db, org_a.id, run, AutomationRunStatus.COMPLETED)
    assert run.status is AutomationRunStatus.COMPLETED

    cancelled = _run(db, org_a, automation_a, user_a, key="idem-cancel")
    update_run_status(db, org_a.id, cancelled, AutomationRunStatus.CANCELLED)

    invalid = _run(db, org_a, automation_a, user_a, key="idem-invalid")
    with pytest.raises(InvalidAutomationTransitionError):
        update_run_status(db, org_a.id, invalid, AutomationRunStatus.COMPLETED)
    with pytest.raises(InvalidAutomationTransitionError):
        update_run_status(db, org_a.id, run, AutomationRunStatus.RUNNING)
    with pytest.raises(InvalidAutomationTransitionError):
        update_run_status(db, org_a.id, cancelled, AutomationRunStatus.RUNNING)


def test_run_status_records_timestamps_and_error_code(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    run = _run(db, org_a, automation_a, user_a)
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=5)

    update_run_status(
        db, org_a.id, run, AutomationRunStatus.RUNNING, started_at=started
    )
    update_run_status(
        db,
        org_a.id,
        run,
        AutomationRunStatus.FAILED,
        finished_at=finished,
        error_code="provider_unavailable",
    )

    assert run.started_at == started
    assert run.finished_at == finished
    assert run.error_code == "provider_unavailable"


def test_approval_transition_requires_pending_and_records_decider(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    run = _run(db, org_a, automation_a, user_a)
    approval = _approval(db, org_a, run, user_a)
    decided_at = datetime.now(UTC)

    decide_approval(
        db, org_a.id, approval, AutomationApprovalStatus.APPROVED, user_a.id, decided_at
    )
    assert approval.status is AutomationApprovalStatus.APPROVED
    assert approval.decided_by == user_a.id
    assert approval.decided_at == decided_at
    with pytest.raises(InvalidAutomationTransitionError):
        decide_approval(
            db, org_a.id, approval, AutomationApprovalStatus.REJECTED, user_a.id, decided_at
        )


def test_uniquitous_names_are_scoped_to_tenant(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    duplicate = Automation(
        organization_id=org_a.id, name=automation_a.name, created_by=user_a.id
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.flush()


def test_same_name_in_other_tenant_is_allowed(db: DBSession) -> None:
    org_a, org_b, user_a, user_b, automation_a, _ = _seed(db)
    other = Automation(
        organization_id=org_b.id, name=automation_a.name, created_by=user_b.id
    )
    db.add(other)
    db.flush()
    assert len(list_automations(db, org_a.id)) == 1
    assert len(list_automations(db, org_b.id)) == 2
    assert user_a.id != user_b.id


def test_version_number_is_unique_per_automation(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    _version(db, org_a, automation_a, user_a)
    duplicate = AutomationVersion(
        organization_id=org_a.id,
        automation_id=automation_a.id,
        version=1,
        trigger={},
        conditions=[],
        actions=[],
        created_by=user_a.id,
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.flush()


def test_next_version_counts_only_versions_of_same_automation(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    other = Automation(
        organization_id=org_a.id, name="Synthetic rule C", created_by=user_a.id
    )
    db.add(other)
    db.flush()
    assert next_version(db, org_a.id, automation_a.id) == 1
    _version(db, org_a, automation_a, user_a, version=1)
    assert next_version(db, org_a.id, automation_a.id) == 2
    _version(db, org_a, other, user_a, version=1)
    assert next_version(db, org_a.id, automation_a.id) == 2


def test_idempotency_key_is_unique_per_automation(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    run = _run(db, org_a, automation_a, user_a, key="same-key")
    assert get_run_by_key(db, org_a.id, automation_a.id, "same-key").id == run.id

    with pytest.raises(IntegrityError):
        _run(db, org_a, automation_a, user_a, key="same-key")


def test_same_idempotency_key_allowed_for_other_automation(db: DBSession) -> None:
    org_a, org_b, user_a, user_b, automation_a, automation_b = _seed(db)
    other = Automation(
        organization_id=org_a.id, name="Synthetic rule C", created_by=user_a.id
    )
    db.add(other)
    db.flush()
    first = _run(db, org_a, automation_a, user_a, key="same-key")
    second = _run(db, org_a, other, user_a, key="same-key")
    third = _run(db, org_b, automation_b, user_b, key="same-key")
    assert len({first.id, second.id, third.id}) == 3


def test_approval_is_unique_per_run_and_action(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    run = _run(db, org_a, automation_a, user_a)
    _approval(db, org_a, run, user_a)
    duplicate = AutomationApproval(
        organization_id=org_a.id,
        run_id=run.id,
        action_type=AutomationActionType.CREATE_MESSAGE_DRAFT,
        payload_hash="0" * 64,
        payload={},
        created_by=user_a.id,
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.flush()


def test_same_action_type_allowed_in_other_run(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    first_run = _run(db, org_a, automation_a, user_a, key="run-1")
    second_run = _run(db, org_a, automation_a, user_a, key="run-2")
    first = _approval(db, org_a, first_run, user_a)
    second = _approval(db, org_a, second_run, user_a)
    assert first.id != second.id
    assert [item.id for item in list_approvals_for_run(db, org_a.id, second_run.id)] == [
        second.id
    ]


def test_cross_tenant_isolation_holds_in_every_repository(db: DBSession) -> None:
    org_a, org_b, user_a, user_b, automation_a, automation_b = _seed(db)
    version = _version(db, org_a, automation_a, user_a)
    run = _run(db, org_a, automation_a, user_a)
    event = create_run_event(
        db,
        organization_id=org_a.id,
        run_id=run.id,
        event_type=AutomationRunEventType.TRIGGER_MATCHED,
        payload={"stage": "interview"},
    )
    approval = _approval(db, org_a, run, user_a)

    assert get_automation(db, org_b.id, automation_a.id) is None
    assert [item.id for item in list_automations(db, org_b.id)] == [automation_b.id]
    assert get_version(db, org_b.id, automation_a.id, 1) is None
    assert get_run_by_key(db, org_b.id, automation_a.id, "idem-synthetic-1") is None
    assert list_runs(db, org_b.id) == []
    assert list_run_events(db, org_b.id, run.id) == []
    assert get_approval(db, org_b.id, approval.id) is None
    assert list_approvals_for_run(db, org_b.id, run.id) == []

    with pytest.raises(AutomationTenantMismatchError):
        next_version(db, org_b.id, automation_a.id)
    with pytest.raises(AutomationTenantMismatchError):
        create_version(
            db,
            organization_id=org_b.id,
            automation_id=automation_a.id,
            version=9,
            trigger={},
            conditions=[],
            actions=[],
            created_by=user_b.id,
        )
    with pytest.raises(AutomationTenantMismatchError):
        create_run(
            db,
            organization_id=org_b.id,
            automation_id=automation_a.id,
            version=1,
            mode=AutomationRunMode.TEST,
            trigger_event_type=AutomationTriggerEventType.APPLICATION_STAGE_CHANGED,
            trigger_event_id=uuid.uuid4(),
            idempotency_key="foreign-key",
            correlation_id=uuid.uuid4(),
            actor_id=user_b.id,
        )
    with pytest.raises(AutomationTenantMismatchError):
        update_run_status(db, org_b.id, run, AutomationRunStatus.RUNNING)
    with pytest.raises(AutomationTenantMismatchError):
        create_run_event(
            db,
            organization_id=org_b.id,
            run_id=run.id,
            event_type=AutomationRunEventType.DRY_RUN,
            payload={},
        )
    with pytest.raises(AutomationTenantMismatchError):
        create_approval(
            db,
            organization_id=org_b.id,
            run_id=run.id,
            action_type=AutomationActionType.RECORD_NOTE,
            payload={},
            created_by=user_b.id,
        )
    with pytest.raises(AutomationTenantMismatchError):
        decide_approval(
            db,
            org_b.id,
            approval,
            AutomationApprovalStatus.APPROVED,
            user_b.id,
            datetime.now(UTC),
        )

    assert version.organization_id == org_a.id
    assert event.organization_id == org_a.id


def test_snapshots_and_event_payloads_are_sanitized(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    run = _run(db, org_a, automation_a, user_a)

    with pytest.raises(ValidationError):
        AutomationVersionCreate(
            trigger=AutomationTrigger(event_type="application.stage_changed"),
            conditions=[],
            actions=[
                AutomationAction(
                    type="create_message_draft",
                    payload={"template_id": "draft-1", "note": "Mail a candidate@test.test"},
                )
            ],
        )
    with pytest.raises(ValidationError):
        AutomationRunEventCreate(
            event_type="dry_run", payload={"api_key": "synthetic-not-a-real-key"}
        )
    with pytest.raises(UnsafeAgentPayloadError):
        create_run_event(
            db,
            organization_id=org_a.id,
            run_id=run.id,
            event_type=AutomationRunEventType.DRY_RUN,
            payload={"password": "synthetic-not-a-real-password"},
        )
    with pytest.raises(UnsafeAgentPayloadError):
        create_version(
            db,
            organization_id=org_a.id,
            automation_id=automation_a.id,
            version=2,
            trigger={"event_type": "application.stage_changed", "cv": "synthetic"},
            conditions=[],
            actions=[],
            created_by=user_a.id,
        )

    version = _version(db, org_a, automation_a, user_a)
    event = create_run_event(
        db,
        organization_id=org_a.id,
        run_id=run.id,
        event_type=AutomationRunEventType.ACTION_PLANNED,
        payload={"note": "Synthetic reminder"},
    )
    approval = _approval(db, org_a, run, user_a)
    values = (
        version.trigger,
        version.conditions,
        version.actions,
        event.payload,
        approval.payload,
    )
    for value in values:
        assert not _SECRET_PATTERN.search(json.dumps(value, ensure_ascii=False))


def test_approval_hash_and_payload_are_canonical(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    run = _run(db, org_a, automation_a, user_a)
    approval = _approval(db, org_a, run, user_a)
    canonical = json.dumps(
        approval.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )

    assert approval.payload_hash == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert len(approval.payload_hash) == 64


def test_models_and_contracts_have_no_score_or_hiring_decision() -> None:
    models = (Automation, AutomationVersion, AutomationRun, AutomationRunEvent, AutomationApproval)
    contracts = (AutomationVersionCreate, AutomationRunCreate, AutomationRunEventCreate)
    for model in models:
        assert not _FORBIDDEN_FIELDS & set(inspect(model).columns.keys())
    for contract in contracts:
        assert not _FORBIDDEN_FIELDS & set(contract.model_fields)


def test_run_event_history_is_queryable_by_run_and_ordered(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    first_run = _run(db, org_a, automation_a, user_a, key="run-events-1")
    second_run = _run(db, org_a, automation_a, user_a, key="run-events-2")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index, event_type in enumerate(
        (
            AutomationRunEventType.TRIGGER_MATCHED,
            AutomationRunEventType.CONDITION_EVALUATED,
            AutomationRunEventType.DRY_RUN,
        )
    ):
        created = create_run_event(
            db,
            organization_id=org_a.id,
            run_id=first_run.id,
            event_type=event_type,
            payload={},
        )
        created.created_at = base + timedelta(seconds=index)
    create_run_event(
        db,
        organization_id=org_a.id,
        run_id=second_run.id,
        event_type=AutomationRunEventType.COMPLETED,
        payload={},
    )
    db.flush()

    history = list_run_events(db, org_a.id, first_run.id)
    assert [item.event_type for item in history] == [
        AutomationRunEventType.TRIGGER_MATCHED,
        AutomationRunEventType.CONDITION_EVALUATED,
        AutomationRunEventType.DRY_RUN,
    ]
    timestamps = [item.created_at.replace(tzinfo=UTC) for item in history]
    assert timestamps == sorted(timestamps)


def test_version_snapshot_cannot_be_updated(db: DBSession) -> None:
    org_a, _, user_a, _, automation_a, _ = _seed(db)
    version = _version(db, org_a, automation_a, user_a)
    assert not hasattr(version, "update")

    version.conditions = [{"field": "job_status", "operator": "eq", "value": "open"}]
    with pytest.raises(AutomationVersionImmutableError):
        db.flush()


def test_trigger_and_conditions_are_closed_contracts() -> None:
    with pytest.raises(ValidationError):
        AutomationTrigger(event_type="candidate.created")
    with pytest.raises(ValidationError):
        AutomationCondition(field="age", operator="eq", value="30")
    with pytest.raises(ValidationError):
        AutomationCondition(field="to_stage", operator="eq", value="unknown")
    with pytest.raises(ValidationError):
        AutomationCondition(field="to_stage", operator="in", value="interview")
    with pytest.raises(ValidationError):
        AutomationAction(type="send_email", payload={"note": "Synthetic"})

    valid = AutomationCondition(field="job_status", operator="in", value=["open", "paused"])
    assert valid.value == ["open", "paused"]
    assert AutomationVersionCreate(
        trigger=AutomationTrigger(event_type="application.stage_changed"),
        conditions=[valid],
        actions=[AutomationAction(type="record_note", payload={"note": "Synthetic note"})],
    ).to_snapshot()["trigger"] == {"event_type": "application.stage_changed"}


def test_input_contracts_forbid_tenant_and_pending_decision() -> None:
    with pytest.raises(ValidationError):
        AutomationRunCreate(
            automation_id=uuid.uuid4(),
            version=1,
            mode="test",
            trigger_event_type="application.stage_changed",
            trigger_event_id=uuid.uuid4(),
            idempotency_key="key-1",
            correlation_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
        )
    with pytest.raises(ValidationError):
        AutomationApprovalDecision(approval_id=uuid.uuid4(), decision="pending")


def test_automation_migration_upgrade_check_and_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "migration-automation.db"
    url = f"sqlite:///{db_file}"

    class _Settings:
        DATABASE_URL = url

    monkeypatch.setattr("app.core.config.get_settings", lambda: _Settings())
    monkeypatch.setattr("logging.config.fileConfig", lambda *_args, **_kwargs: None)
    # `test_auth` recarga `app.db.base`; env.py debe ver el Base con modelos registrados.
    monkeypatch.setattr("app.db.base.Base", Base, raising=True)
    api_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(api_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(api_root / "migrations"))

    command.upgrade(alembic_config, "0011_interviews")
    engine = create_engine(url)
    try:
        before = set(inspect(engine).get_table_names())
        assert not _AUTOMATION_TABLES & before

        command.upgrade(alembic_config, "head")
        after = set(inspect(engine).get_table_names())
        assert _AUTOMATION_TABLES <= after
        command.check(alembic_config)

        command.downgrade(alembic_config, "0011_interviews")
        reverted = set(inspect(engine).get_table_names())
        assert not _AUTOMATION_TABLES & reverted
    finally:
        engine.dispose()


def test_run_queried_by_status_stays_tenant_scoped(db: DBSession) -> None:
    org_a, org_b, user_a, user_b, automation_a, automation_b = _seed(db)
    run_a = _run(db, org_a, automation_a, user_a)
    run_b = _run(db, org_b, automation_b, user_b, key="other-tenant-key")
    update_run_status(db, org_a.id, run_a, AutomationRunStatus.RUNNING)
    update_run_status(db, org_b.id, run_b, AutomationRunStatus.RUNNING)

    assert [item.id for item in list_runs(db, org_a.id, status=AutomationRunStatus.RUNNING)] == [
        run_a.id
    ]
