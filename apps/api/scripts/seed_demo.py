from __future__ import annotations

import json
import sys

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

import app.main  # noqa: F401  # regula las tablas en Base.metadata al importar rutas
from app.applications.service import create_application
from app.candidates.service import create_candidate
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal
from app.identity.models import Invitation, Organization, PasswordResetToken, Session, User
from app.identity.service import create_organization, register_user
from app.jobs.service import create_job

DEMO_EMAIL = "demo.owner@example.test"
DEMO_PASSWORD = "DemoSynthetic123"
DEMO_NAME = "Propietario demo"
DEMO_ORG_NAME = "Organización demo"
DEMO_ORG_SLUG = "demo-talentos"
DEMO_JOB_TITLE = "Analista de selección · demo"
DEMO_CANDIDATES = (
    ("Candidato sintético 1", "candidate1.demo@example.test"),
    ("Candidato sintético 2", "candidate2.demo@example.test"),
    ("Candidato sintético 3", "candidate3.demo@example.test"),
)


def reset_demo(db: DBSession) -> None:
    """Borra solo la organización y el usuario de demo; nunca toca otros tenants."""
    organization = db.scalar(select(Organization).where(Organization.slug == DEMO_ORG_SLUG))
    users = list(db.scalars(select(User).where(User.email == DEMO_EMAIL)).all())
    user_ids = [user.id for user in users]

    if user_ids:
        db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id.in_(user_ids)))
        db.execute(delete(Session).where(Session.user_id.in_(user_ids)))
        db.execute(delete(Invitation).where(Invitation.email == DEMO_EMAIL))

    if organization is not None:
        for table in reversed(Base.metadata.sorted_tables):
            if "organization_id" in table.c:
                db.execute(delete(table).where(table.c.organization_id == organization.id))
        db.execute(delete(Organization).where(Organization.id == organization.id))

    if user_ids:
        db.execute(delete(User).where(User.id.in_(user_ids)))
    db.commit()


def seed_demo(db: DBSession) -> dict[str, str | int]:
    """Crea datos sintéticos reproducibles; llamarla dos veces no duplica filas."""
    reset_demo(db)

    user = register_user(db, email=DEMO_EMAIL, password=DEMO_PASSWORD, name=DEMO_NAME)
    organization = create_organization(
        db, creator=user, name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG
    )
    job = create_job(
        db,
        organization_id=organization.id,
        owner_id=user.id,
        title=DEMO_JOB_TITLE,
        description="Vacante sintética para recorrer el pipeline de demostración.",
        modality="híbrido",
        location="Madrid",
        seniority="mid",
        actor_id=user.id,
    )

    candidates = [
        create_candidate(
            db,
            organization_id=organization.id,
            name=name,
            email=email,
            location="Remoto",
            actor_id=user.id,
        )
        for name, email in DEMO_CANDIDATES
    ]
    for candidate in candidates:
        create_application(
            db,
            organization_id=organization.id,
            job_id=job.id,
            candidate_id=candidate.id,
            actor_id=user.id,
        )

    return {
        "organization_id": str(organization.id),
        "user_id": str(user.id),
        "job_id": str(job.id),
        "candidates": len(candidates),
    }


def main() -> None:
    settings = get_settings()
    if settings.APP_ENV not in {"local", "test"}:
        raise SystemExit("El seed de demo solo se permite en APP_ENV=local o test.")

    mode = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if mode not in {"seed", "reset"}:
        raise SystemExit("Uso: python -m scripts.seed_demo [seed|reset]")

    with SessionLocal() as db:
        result = seed_demo(db) if mode == "seed" else reset_demo(db)
    print(json.dumps(result if result is not None else {"reset": True}, sort_keys=True))


if __name__ == "__main__":
    main()
