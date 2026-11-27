from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

import app.main  # noqa: F401  # regula las tablas en Base.metadata al importar rutas
from app.agents import repositories as agents_repositories
from app.agents.contracts import MATCHING_REVIEW_WORKFLOW
from app.agents.interview_assistant import PROMPT_VERSION as INTERVIEW_PROMPT_VERSION
from app.agents.matching_analyst import PROMPT_VERSION as MATCHING_PROMPT_VERSION
from app.agents.models import AgentEvent, AgentEventType, AgentRun, AgentRunStatus, ApprovalStatus
from app.applications.models import Application, ApplicationStage, StageChange
from app.applications.service import create_application
from app.assessment import repositories as assessment_repositories
from app.assessment.models import (
    Assessment,
    AssessmentStatus,
    RequirementEvaluation,
    RequirementEvaluationStatus,
)
from app.automation import service as automation_service
from app.automation.models import AutomationActionType, AutomationTriggerEventType
from app.automation.schemas import (
    AutomationAction,
    AutomationActionPayload,
    AutomationCondition,
    AutomationConditionField,
    AutomationConditionOperator,
    AutomationTrigger,
    AutomationVersionCreate,
)
from app.candidates.models import Candidate, CandidateNote
from app.candidates.service import create_candidate
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal
from app.documents.extraction import (
    EXTRACTION_MODEL,
    EXTRACTION_PROMPT_VERSION,
    EXTRACTION_PROVIDER,
)
from app.documents.models import (
    Document,
    DocumentExtraction,
    DocumentStatus,
    ExtractedField,
    ExtractedFieldName,
    ExtractedFieldStatus,
    ExtractionStatus,
)
from app.identity.models import (
    Invitation,
    Membership,
    MembershipRole,
    Organization,
    PasswordResetToken,
    Session,
    User,
)
from app.identity.service import create_organization, register_user
from app.integrations import repositories as integrations_repositories
from app.integrations.models import (
    EmailLanguage,
    EmailTemplate,
    Integration,
    IntegrationProvider,
    IntegrationStatus,
)
from app.interviews.models import (
    InterviewGuide,
    InterviewGuideStatus,
    InterviewQuestion,
    InterviewQuestionCategory,
    InterviewQuestionStatus,
)
from app.interviews.service import (
    DETERMINISTIC_MODEL_VERSION as INTERVIEW_MODEL_VERSION,
)
from app.jobs import service as jobs_service
from app.jobs.models import (
    Job,
    JobRequirement,
    JobVersion,
    RequirementCategory,
    RequirementImportance,
)
from app.jobs.service import create_job

DEMO_EMAIL = "demo.owner@example.test"
DEMO_PASSWORD = "DemoSynthetic123"
DEMO_NAME = "Propietario demo"
SUPERADMIN_EMAIL = "superadmin.demo@example.test"
SUPERADMIN_NAME = "Superadmin demo"
SUPERADMIN_PASSWORD_ENV = "TALENTOS_SUPERADMIN_PASSWORD"
DEMO_ORG_NAME = "Organización demo"
DEMO_ORG_SLUG = "demo-talentos"
DEMO_JOB_TITLE = "Analista de selección · demo"
DEMO_CANDIDATES = (
    ("Candidato sintético 1", "candidate1.demo@example.test"),
    ("Candidato sintético 2", "candidate2.demo@example.test"),
    ("Candidato sintético 3", "candidate3.demo@example.test"),
    ("Candidato sintético 4", "candidate4.demo@example.test"),
    ("Candidato sintético 5", "candidate5.demo@example.test"),
)
DEMO_PAGE_TEXTS = (
    "Perfil sintetico 1\nSkills: Python, SQL\nProyecto: automatizacion interna",
    "Perfil sintetico 2\nSkills: Python basico\nProyecto: apoyo en procesos",
    "Perfil sintetico 3\nExperiencia: atencion al cliente",
    "Perfil sintetico 4\nSkills: Python en revision",
)
DEMO_REQUIREMENTS = (
    (
        RequirementCategory.SKILL,
        "Python aplicado a automatizaciones",
        RequirementImportance.REQUIRED,
        "intermedio",
        "Proyectos con Python",
        0.6,
        "Requisito central del puesto demo",
    ),
    (
        RequirementCategory.EXPERIENCE,
        "Experiencia en procesos de selección",
        RequirementImportance.REQUIRED,
        "al menos un año",
        "Procesos documentados",
        0.3,
        "Requisito de ejecución del puesto demo",
    ),
    (
        RequirementCategory.LANGUAGE,
        "Comunicación en español",
        RequirementImportance.DESIRABLE,
        "nivel profesional",
        "Entrevistas en español",
        0.1,
        "Requisito complementario del puesto demo",
    ),
)


def _delete_demo_children(db: DBSession, organization_id: uuid.UUID) -> None:
    """Borra hijos sin `organization_id` antes de borrar sus padres del tenant."""
    job_ids = select(Job.id).where(Job.organization_id == organization_id)
    candidate_ids = select(Candidate.id).where(Candidate.organization_id == organization_id)
    application_ids = select(Application.id).where(Application.organization_id == organization_id)
    document_ids = select(Document.id).where(Document.organization_id == organization_id)
    assessment_ids = select(Assessment.id).where(Assessment.organization_id == organization_id)
    run_ids = select(AgentRun.id).where(AgentRun.organization_id == organization_id)
    extraction_ids = select(DocumentExtraction.id).where(
        DocumentExtraction.document_id.in_(document_ids)
    )

    db.execute(delete(ExtractedField).where(ExtractedField.extraction_id.in_(extraction_ids)))
    db.execute(delete(DocumentExtraction).where(DocumentExtraction.document_id.in_(document_ids)))
    db.execute(
        delete(RequirementEvaluation).where(
            RequirementEvaluation.assessment_id.in_(assessment_ids)
        )
    )
    db.execute(delete(JobRequirement).where(JobRequirement.job_id.in_(job_ids)))
    db.execute(delete(JobVersion).where(JobVersion.job_id.in_(job_ids)))
    db.execute(delete(AgentEvent).where(AgentEvent.agent_run_id.in_(run_ids)))
    db.execute(delete(CandidateNote).where(CandidateNote.candidate_id.in_(candidate_ids)))
    db.execute(delete(StageChange).where(StageChange.application_id.in_(application_ids)))


def reset_demo(db: DBSession) -> None:
    """Borra solo la organización y el usuario de demo; nunca toca otros tenants."""
    organization = db.scalar(select(Organization).where(Organization.slug == DEMO_ORG_SLUG))
    users = list(
        db.scalars(select(User).where(User.email.in_({DEMO_EMAIL, SUPERADMIN_EMAIL}))).all()
    )
    user_ids = [user.id for user in users]

    if user_ids:
        db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id.in_(user_ids)))
        db.execute(delete(Session).where(Session.user_id.in_(user_ids)))
        db.execute(
            delete(Invitation).where(Invitation.email.in_({DEMO_EMAIL, SUPERADMIN_EMAIL}))
        )

    if organization is not None:
        _delete_demo_children(db, organization.id)
        for table in reversed(Base.metadata.sorted_tables):
            if "organization_id" in table.c:
                db.execute(delete(table).where(table.c.organization_id == organization.id))
        db.execute(delete(Organization).where(Organization.id == organization.id))

    if user_ids:
        db.execute(delete(User).where(User.id.in_(user_ids)))
    db.commit()


def _seed_versions(
    db: DBSession, organization: Organization, job: Job, user: User
) -> tuple[list[JobRequirement], JobVersion, JobVersion]:
    requirements = [
        jobs_service.add_requirement(
            db,
            organization_id=organization.id,
            job_id=job.id,
            category=category,
            description=description,
            importance=importance,
            expected_level=expected_level,
            acceptable_evidence=[evidence],
            weight=weight,
            weight_justification=justification,
            actor_id=user.id,
        )
        for category, description, importance, expected_level, evidence, weight, justification in (
            DEMO_REQUIREMENTS
        )
    ]
    first_version = jobs_service.create_version(
        db, organization_id=organization.id, job_id=job.id, actor_id=user.id
    )
    jobs_service.update_requirement(
        db,
        organization_id=organization.id,
        job_id=job.id,
        requirement_id=requirements[1].id,
        description="Experiencia en selección de personal",
        weight=0.35,
        weight_justification="Ajuste demo tras la primera versión",
        actor_id=user.id,
    )
    second_version = jobs_service.create_version(
        db, organization_id=organization.id, job_id=job.id, actor_id=user.id
    )
    return requirements, first_version, second_version


def _seed_documents(
    db: DBSession, organization: Organization, user: User, candidates: list[Candidate]
) -> tuple[list[Document], list[DocumentExtraction], list[ExtractedField]]:
    documents: list[Document] = []
    extractions: list[DocumentExtraction] = []
    fields: list[ExtractedField] = []
    statuses = (
        ExtractedFieldStatus.CONFIRMED,
        ExtractedFieldStatus.CORRECTED,
        ExtractedFieldStatus.MISSING,
        ExtractedFieldStatus.NEEDS_REVIEW,
    )
    quotes = ("Python, SQL", "Python basico", "", "Python en revision")

    for index, (page_text, status, quote) in enumerate(
        zip(DEMO_PAGE_TEXTS, statuses, quotes, strict=True), start=1
    ):
        encoded = page_text.encode("utf-8")
        document = Document(
            organization_id=organization.id,
            candidate_id=candidates[index - 1].id,
            uploaded_by=user.id,
            original_filename=f"cv_sintetico_{index}.pdf",
            internal_name=f"seed_cv_sintetico_{index}.pdf",
            content_type="application/pdf",
            extension=".pdf",
            size_bytes=len(encoded),
            checksum_sha256=hashlib.sha256(encoded).hexdigest(),
            status=DocumentStatus.PROCESSED,
            page_count=1,
        )
        db.add(document)
        db.flush()

        extraction = DocumentExtraction(
            document_id=document.id,
            provider=EXTRACTION_PROVIDER,
            model=EXTRACTION_MODEL,
            prompt_version=EXTRACTION_PROMPT_VERSION,
            status=ExtractionStatus.COMPLETED,
            pages=[
                {
                    "page": 1,
                    "text": page_text,
                    "start_offset": 0,
                    "end_offset": len(page_text),
                }
            ],
        )
        db.add(extraction)
        db.flush()

        evidence = (
            [
                {
                    "document_id": str(document.id),
                    "page": 1,
                    "quote": quote,
                    "offset": page_text.find(quote),
                }
            ]
            if quote
            else []
        )
        field = ExtractedField(
            extraction_id=extraction.id,
            field_name=ExtractedFieldName.SKILLS,
            value=["Python", "SQL"] if status is ExtractedFieldStatus.CONFIRMED else ["Python"],
            status=status,
            evidence=evidence,
            confirmed_by=user.id if status is ExtractedFieldStatus.CONFIRMED else None,
            confirmed_at=datetime.now(UTC) if status is ExtractedFieldStatus.CONFIRMED else None,
        )
        db.add(field)
        db.flush()
        documents.append(document)
        extractions.append(extraction)
        fields.append(field)

    return documents, extractions, fields


def _seed_assessment(
    db: DBSession,
    organization: Organization,
    user: User,
    application: Application,
    candidate: Candidate,
    version: JobVersion,
    document: Document,
    page_text: str,
) -> None:
    requirement_ids = [uuid.UUID(str(item["id"])) for item in version.snapshot["requirements"]]
    evidence = [
        {
            "document_id": str(document.id),
            "field_name": ExtractedFieldName.SKILLS.value,
            "page": 1,
            "quote": "Python, SQL",
            "offset": page_text.find("Python, SQL"),
        }
    ]
    assessment = assessment_repositories.create_assessment(
        db,
        organization_id=organization.id,
        application_id=application.id,
        job_version_id=version.id,
        candidate_id=candidate.id,
        created_by=user.id,
        model_version="seed-demo-mock-v1",
        prompt_version=MATCHING_PROMPT_VERSION,
    )
    statuses = (
        (RequirementEvaluationStatus.SUPPORTED, evidence, [], False),
        (
            RequirementEvaluationStatus.PARTIAL,
            [{**evidence[0], "quote": "Python", "offset": page_text.find("Python")}],
            ["Falta profundidad"],
            True,
        ),
        (RequirementEvaluationStatus.NOT_FOUND, [], ["Sin experiencia documentada"], False),
        (RequirementEvaluationStatus.NEEDS_REVIEW, [], ["Cita en revisión"], True),
    )
    for requirement_id, (status, items, limitations, review_required) in zip(
        requirement_ids + requirement_ids[:1], statuses, strict=True
    ):
        assessment_repositories.save_evaluation(
            db,
            assessment_id=assessment.id,
            requirement_id=requirement_id,
            status=status,
            explanation="Evaluación sintética de demostración",
            evidence=items,
            limitations=limitations,
            review_required=review_required,
        )
    assessment_repositories.update_summary(
        db,
        assessment,
        status=AssessmentStatus.NEEDS_REVIEW,
        summary={"strengths": ["Python"], "gaps": ["Experiencia"], "questions": ["Proyectos"]},
        limitations=["Datos sintéticos de demostración"],
    )


def _seed_interview_guide(
    db: DBSession,
    organization: Organization,
    user: User,
    application: Application,
    version: JobVersion,
) -> None:
    requirement_ids = [uuid.UUID(str(item["id"])) for item in version.snapshot["requirements"]]
    guide = InterviewGuide(
        organization_id=organization.id,
        application_id=application.id,
        version=1,
        title="Guía de entrevista demo v1",
        status=InterviewGuideStatus.DRAFT,
        created_by=user.id,
    )
    db.add(guide)
    db.flush()
    questions = (
        (1, requirement_ids[0], InterviewQuestionCategory.TECHNICAL, InterviewQuestionStatus.DRAFT),
        (
            2,
            requirement_ids[1],
            InterviewQuestionCategory.DEEP_DIVE,
            InterviewQuestionStatus.REJECTED,
        ),
    )
    for position, requirement_id, category, status in questions:
        db.add(
            InterviewQuestion(
                organization_id=organization.id,
                guide_id=guide.id,
                requirement_id=requirement_id,
                position=position,
                category=category,
                question=f"Pregunta sintética {position} sobre evidencia del puesto demo",
                evidence_focus="Evidencia confirmada en el CV sintético",
                competency="Competencia demo",
                status=status,
                model_version=INTERVIEW_MODEL_VERSION,
                prompt_version=INTERVIEW_PROMPT_VERSION,
                created_by=user.id,
            )
        )
    db.flush()


def _seed_email_draft(
    db: DBSession, organization: Organization, user: User, candidate: Candidate
) -> None:
    integration = Integration(
        organization_id=organization.id,
        provider=IntegrationProvider.EMAIL_SANDBOX,
        encrypted_config_ref="seed-sandbox-no-secret",
        key_id="demokey00001",
        status=IntegrationStatus.ACTIVE,
        config_version=1,
    )
    db.add(integration)
    db.flush()
    integrations_repositories.create_email_draft(
        db,
        organization_id=organization.id,
        integration_id=integration.id,
        candidate_id=candidate.id,
        template=EmailTemplate.INITIAL_CONTACT,
        topic="Proceso sintético demo",
        language=EmailLanguage.ES,
        call_to_action="Revisar mensaje sandbox",
        subject="[TalentOS][es] Contacto inicial: Proceso sintético demo",
        body_hash=hashlib.sha256(b"seed-demo-email-sintetico").hexdigest(),
        requested_by=user.id,
    )


def _seed_automation(db: DBSession, organization: Organization, user: User) -> None:
    version = AutomationVersionCreate(
        trigger=AutomationTrigger(
            event_type=AutomationTriggerEventType.APPLICATION_STAGE_CHANGED
        ),
        conditions=[
            AutomationCondition(
                field=AutomationConditionField.TO_STAGE,
                operator=AutomationConditionOperator.EQ,
                value=ApplicationStage.SCREENING.value,
            )
        ],
        actions=[
            AutomationAction(
                type=AutomationActionType.RECORD_NOTE,
                payload=AutomationActionPayload(note="Revisar etapa screening demo"),
            )
        ],
    )
    automation_service.create_automation(
        db,
        organization_id=organization.id,
        actor_id=user.id,
        actor_role=MembershipRole.OWNER,
        name="Regla demo screening",
        version=version,
    )


def _seed_approvals(
    db: DBSession, organization: Organization, user: User, application: Application
) -> None:
    decisions = (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)
    for index, decision in enumerate(decisions, start=1):
        token = f"demo:matching:{application.id}:{index}"
        correlation_id = uuid.uuid5(uuid.NAMESPACE_URL, f"talentos-demo:correlation:{index}")
        run = agents_repositories.get_or_create_agent_run(
            db,
            organization_id=organization.id,
            workflow=MATCHING_REVIEW_WORKFLOW.workflow,
            version=MATCHING_REVIEW_WORKFLOW.version,
            idempotency_key=token,
            correlation_id=correlation_id,
            actor_id=user.id,
            input_ref=str(application.id),
        )
        agents_repositories.update_agent_run_status(db, run, AgentRunStatus.RUNNING)
        agents_repositories.update_agent_run_status(db, run, AgentRunStatus.WAITING_APPROVAL)
        approval = agents_repositories.create_approval(
            db,
            organization_id=organization.id,
            agent_run_id=run.id,
            action_type=MATCHING_REVIEW_WORKFLOW.approval_action_type,
            payload={
                "action_type": MATCHING_REVIEW_WORKFLOW.approval_action_type,
                "application_id": str(application.id),
                "requested_by": str(user.id),
                "requested_at": datetime.now(UTC).isoformat(),
                "idempotency_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            },
        )
        agents_repositories.create_agent_event(
            db,
            organization_id=organization.id,
            agent_run_id=run.id,
            event_type=AgentEventType.APPROVAL_REQUESTED,
            payload={
                "organization_id": str(organization.id),
                "actor_id": str(user.id),
                "correlation_id": str(correlation_id),
                "approval_id": str(approval.id),
                "workflow": run.workflow,
                "version": run.version,
            },
            correlation_id=correlation_id,
        )
        agents_repositories.decide_approval(
            db,
            approval,
            decision=decision,
            decided_by=user.id,
            decided_at=datetime.now(UTC),
        )
        agents_repositories.create_agent_event(
            db,
            organization_id=organization.id,
            agent_run_id=run.id,
            event_type=AgentEventType.APPROVAL_RESOLVED,
            payload={
                "organization_id": str(organization.id),
                "actor_id": str(user.id),
                "correlation_id": str(correlation_id),
                "approval_id": str(approval.id),
                "decision": decision.value,
                "workflow": run.workflow,
                "version": run.version,
            },
            correlation_id=correlation_id,
        )
        final_status = (
            AgentRunStatus.COMPLETED
            if decision is ApprovalStatus.APPROVED
            else AgentRunStatus.FAILED
        )
        agents_repositories.update_agent_run_status(db, run, final_status)


def seed_demo(db: DBSession) -> dict[str, str | int]:
    """Crea datos sintéticos reproducibles; llamarla dos veces no duplica filas."""
    reset_demo(db)

    user = register_user(db, email=DEMO_EMAIL, password=DEMO_PASSWORD, name=DEMO_NAME)
    organization = create_organization(
        db, creator=user, name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG
    )
    superadmin_password = os.environ.get(SUPERADMIN_PASSWORD_ENV, "").strip()
    if superadmin_password:
        if len(superadmin_password) < 12:
            raise SystemExit("La contraseña del superadmin debe tener al menos 12 caracteres.")
        superadmin = register_user(
            db,
            email=SUPERADMIN_EMAIL,
            password=superadmin_password,
            name=SUPERADMIN_NAME,
        )
        superadmin.is_superadmin = True
        db.add(
            Membership(
                organization_id=organization.id,
                user_id=superadmin.id,
                role=MembershipRole.VIEWER,
            )
        )
        db.commit()
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

    requirements, first_version, second_version = _seed_versions(db, organization, job, user)
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
    applications = [
        create_application(
            db,
            organization_id=organization.id,
            job_id=job.id,
            candidate_id=candidate.id,
            actor_id=user.id,
        )
        for candidate in candidates
    ]
    documents, extractions, fields = _seed_documents(db, organization, user, candidates)
    _seed_assessment(
        db,
        organization,
        user,
        applications[0],
        candidates[0],
        second_version,
        documents[0],
        DEMO_PAGE_TEXTS[0],
    )
    _seed_interview_guide(db, organization, user, applications[0], second_version)
    _seed_email_draft(db, organization, user, candidates[0])
    _seed_automation(db, organization, user)
    _seed_approvals(db, organization, user, applications[0])

    return {
        "organization_id": str(organization.id),
        "user_id": str(user.id),
        "job_id": str(job.id),
        "first_job_version_id": str(first_version.id),
        "job_version_id": str(second_version.id),
        "candidates": len(candidates),
        "applications": len(applications),
        "requirements": len(requirements),
        "job_versions": 2,
        "documents": len(documents),
        "extractions": len(extractions),
        "extracted_fields": len(fields),
        "superadmin": bool(superadmin_password),
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
