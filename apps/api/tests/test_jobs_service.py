from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession

# Registrar tablas al importar: `test_auth` recarga `app.db.base` al terminar y
# los modelos importados después quedarían en una metadata distinta de `Base`.
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.db.base import Base

if TYPE_CHECKING:
    from app.identity.models import Organization, User


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[DBSession]:
    with DBSession(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def tenants(db: DBSession) -> tuple[Organization, Organization, User, User]:
    from app.identity.models import Membership, MembershipRole, Organization, User

    org_a = Organization(name="Org A", slug="org-a")
    org_b = Organization(name="Org B", slug="org-b")
    user_a = User(email="owner-a@example.test", password_hash="synthetic-hash", name="Owner A")
    user_b = User(email="owner-b@example.test", password_hash="synthetic-hash", name="Owner B")
    db.add_all([org_a, org_b, user_a, user_b])
    db.flush()
    db.add_all(
        [
            Membership(organization_id=org_a.id, user_id=user_a.id, role=MembershipRole.OWNER),
            Membership(organization_id=org_b.id, user_id=user_b.id, role=MembershipRole.OWNER),
        ]
    )
    db.flush()
    return org_a, org_b, user_a, user_b


def test_create_job_rejects_blank_title(
    db: DBSession, tenants: tuple[Organization, Organization, User, User]
) -> None:
    from app.jobs.service import JobValidationError, create_job

    org_a, _, user_a, _ = tenants

    with pytest.raises(JobValidationError):
        create_job(db, organization_id=org_a.id, owner_id=user_a.id, title="   ")


def test_owner_from_other_organization_is_rejected(
    db: DBSession, tenants: tuple[Organization, Organization, User, User]
) -> None:
    from app.jobs.service import OwnerNotMemberError, create_job, update_job

    org_a, _, user_a, user_b = tenants

    with pytest.raises(OwnerNotMemberError):
        create_job(db, organization_id=org_a.id, owner_id=user_b.id, title="Synthetic role")

    job = create_job(db, organization_id=org_a.id, owner_id=user_a.id, title="Synthetic role")
    with pytest.raises(OwnerNotMemberError):
        update_job(db, organization_id=org_a.id, job_id=job.id, owner_id=user_b.id)

    assert job.owner_id == user_a.id


def test_weight_without_justification_is_rejected(
    db: DBSession, tenants: tuple[Organization, Organization, User, User]
) -> None:
    from app.jobs.models import RequirementCategory, RequirementImportance
    from app.jobs.service import JobValidationError, add_requirement, create_job

    org_a, _, user_a, _ = tenants
    job = create_job(db, organization_id=org_a.id, owner_id=user_a.id, title="Synthetic role")
    kwargs = {
        "organization_id": org_a.id,
        "job_id": job.id,
        "category": RequirementCategory.SKILL,
        "description": "Synthetic skill",
        "importance": RequirementImportance.REQUIRED,
    }

    with pytest.raises(JobValidationError):
        add_requirement(db, **kwargs, weight=0.5)

    with pytest.raises(JobValidationError):
        add_requirement(db, **kwargs, weight=1.5, weight_justification="Out of range")

    requirement = add_requirement(
        db,
        **kwargs,
        acceptable_evidence=["portfolio"],
        weight=0.5,
        weight_justification="Peso explicado",
    )
    assert requirement.weight == 0.5
    assert requirement.weight_justification == "Peso explicado"
    assert requirement.acceptable_evidence == ["portfolio"]


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "closed"),
        ("draft", "archived"),
        ("open", "draft"),
        ("paused", "draft"),
        ("closed", "open"),
        ("closed", "paused"),
        ("archived", "draft"),
        ("archived", "open"),
        ("archived", "archived"),
    ],
)
def test_invalid_status_transitions_are_rejected(
    db: DBSession,
    tenants: tuple[Organization, Organization, User, User],
    current: str,
    target: str,
) -> None:
    from app.jobs.models import JobStatus
    from app.jobs.service import InvalidJobStatusTransitionError, change_status, create_job

    org_a, _, user_a, _ = tenants
    job = create_job(db, organization_id=org_a.id, owner_id=user_a.id, title="Synthetic role")
    job.status = JobStatus(current)
    db.flush()

    with pytest.raises(InvalidJobStatusTransitionError):
        change_status(
            db,
            organization_id=org_a.id,
            job_id=job.id,
            new_status=JobStatus(target),
        )

    assert job.status is JobStatus(current)


def test_allowed_status_transitions_are_applied(
    db: DBSession, tenants: tuple[Organization, Organization, User, User]
) -> None:
    from app.jobs.models import JobStatus
    from app.jobs.service import change_status, create_job

    org_a, _, user_a, _ = tenants
    job = create_job(db, organization_id=org_a.id, owner_id=user_a.id, title="Synthetic role")

    for target in (
        JobStatus.OPEN,
        JobStatus.PAUSED,
        JobStatus.OPEN,
        JobStatus.CLOSED,
        JobStatus.ARCHIVED,
    ):
        changed = change_status(
            db, organization_id=org_a.id, job_id=job.id, new_status=target
        )
        assert changed.status is target


def test_repositories_are_tenant_scoped_and_read_only(
    db: DBSession, tenants: tuple[Organization, Organization, User, User]
) -> None:
    from app.jobs.models import (
        Job,
        JobRequirement,
        JobStatus,
        JobVersion,
        RequirementCategory,
        RequirementImportance,
    )
    from app.jobs.repositories import (
        get_job,
        get_requirement,
        get_version,
        list_jobs,
        list_requirements,
    )

    org_a, org_b, user_a, user_b = tenants
    job_a = Job(organization_id=org_a.id, title="Role A", owner_id=user_a.id, status=JobStatus.OPEN)
    job_b = Job(organization_id=org_b.id, title="Role B", owner_id=user_b.id)
    db.add_all([job_a, job_b])
    db.flush()
    requirement_a = JobRequirement(
        job_id=job_a.id,
        category=RequirementCategory.SKILL,
        description="Skill A",
        importance=RequirementImportance.REQUIRED,
    )
    requirement_b = JobRequirement(
        job_id=job_b.id,
        category=RequirementCategory.SKILL,
        description="Skill B",
        importance=RequirementImportance.DESIRABLE,
    )
    version_a = JobVersion(job_id=job_a.id, version=1, snapshot={"job": {"title": "Role A"}})
    version_b = JobVersion(job_id=job_b.id, version=1, snapshot={"job": {"title": "Role B"}})
    db.add_all([requirement_a, requirement_b, version_a, version_b])
    db.flush()

    before_jobs = len(db.scalars(select(Job)).all())
    before_requirements = len(db.scalars(select(JobRequirement)).all())
    before_versions = len(db.scalars(select(JobVersion)).all())

    assert get_job(db, org_a.id, job_a.id) is job_a
    assert get_job(db, org_b.id, job_a.id) is None
    assert [job.id for job in list_jobs(db, org_a.id)] == [job_a.id]
    assert [job.id for job in list_jobs(db, org_b.id, status=JobStatus.DRAFT)] == [job_b.id]
    assert [job.id for job in list_jobs(db, org_a.id, status=JobStatus.OPEN)] == [job_a.id]

    assert get_requirement(db, org_a.id, requirement_a.id) is requirement_a
    assert get_requirement(db, org_b.id, requirement_a.id) is None
    assert [req.id for req in list_requirements(db, org_a.id, job_a.id)] == [requirement_a.id]
    assert list_requirements(db, org_b.id, job_a.id) == []

    assert get_version(db, org_a.id, job_a.id, 1) is version_a
    assert get_version(db, org_b.id, job_a.id, 1) is None
    assert get_version(db, org_a.id, job_b.id, 1) is None

    assert len(db.scalars(select(Job)).all()) == before_jobs
    assert len(db.scalars(select(JobRequirement)).all()) == before_requirements
    assert len(db.scalars(select(JobVersion)).all()) == before_versions


def test_create_version_increments_and_snapshot_stays_immutable(
    db: DBSession, tenants: tuple[Organization, Organization, User, User]
) -> None:
    from app.jobs.models import RequirementCategory, RequirementImportance
    from app.jobs.service import (
        add_requirement,
        create_job,
        create_version,
        update_job,
    )

    org_a, _, user_a, _ = tenants
    job = create_job(
        db,
        organization_id=org_a.id,
        owner_id=user_a.id,
        title="Original title",
        description="Original description",
    )
    add_requirement(
        db,
        organization_id=org_a.id,
        job_id=job.id,
        category=RequirementCategory.SKILL,
        description="Original skill",
        importance=RequirementImportance.REQUIRED,
        acceptable_evidence=["portfolio"],
        weight=0.5,
        weight_justification="Peso explicado",
    )

    first = create_version(db, organization_id=org_a.id, job_id=job.id)
    assert first.version == 1
    assert first.snapshot["job"]["title"] == "Original title"
    assert len(first.snapshot["requirements"]) == 1

    update_job(
        db,
        organization_id=org_a.id,
        job_id=job.id,
        title="Changed title",
        description="Changed description",
    )
    add_requirement(
        db,
        organization_id=org_a.id,
        job_id=job.id,
        category=RequirementCategory.EXPERIENCE,
        description="Added skill",
        importance=RequirementImportance.DESIRABLE,
    )
    second = create_version(db, organization_id=org_a.id, job_id=job.id)

    assert second.version == 2
    assert first.snapshot["job"]["title"] == "Original title"
    assert len(first.snapshot["requirements"]) == 1
    assert second.snapshot["job"]["title"] == "Changed title"
    assert len(second.snapshot["requirements"]) == 2
