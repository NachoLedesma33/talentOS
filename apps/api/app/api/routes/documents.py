from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session as DBSession

from app.db.session import get_db
from app.documents import service as documents_service
from app.documents import tokens
from app.documents.models import Document
from app.documents.schemas import (
    DocumentListResponse,
    DocumentResponse,
    DownloadUrlResponse,
    ExtractionResponse,
    ReviewRequest,
    ReviewResponse,
    ReviewSummaryResponse,
)
from app.documents.validation import MAX_SIZE_BYTES, UploadValidationError
from app.identity.dependencies import (
    get_current_organization,
    get_current_user,
    require_roles,
    verify_origin,
)
from app.identity.models import Membership, MembershipRole, Organization, User

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

DbDependency = Annotated[DBSession, Depends(get_db)]
OriginChecked = Annotated[None, Depends(verify_origin)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentOrganization = Annotated[Organization, Depends(get_current_organization)]
WriteMember = Annotated[
    Membership,
    Depends(
        require_roles(
            MembershipRole.OWNER,
            MembershipRole.ADMIN,
            MembershipRole.RECRUITER,
        )
    ),
]

_NOT_FOUND_MESSAGE = "Documento no encontrado."


def _validation_error(request: Request, code: str) -> JSONResponse:
    """Error 400 con código estable; sin nombre de archivo, ruta ni payload."""
    request_id: object = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": {
                "code": code,
                "message": "Solicitud inválida; revise el archivo enviado.",
                "request_id": str(request_id),
            }
        },
    )


def _review_error(exc: documents_service.DocumentsDomainError) -> HTTPException:
    """Traduce códigos de dominio sin filtrar valores de campo ni evidencia."""
    if exc.code == "forbidden":
        return HTTPException(status.HTTP_403_FORBIDDEN, detail="Rol insuficiente.")
    if exc.code == "review_required":
        return HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Revisión individual requerida antes de confirmar en bloque.",
        )
    if exc.code == "not_found":
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE)
    return HTTPException(
        status.HTTP_409_CONFLICT, detail="Estado de extracción inválido."
    )


@router.get("/", response_model=DocumentListResponse)
def list_documents(
    active_organization: CurrentOrganization,
    db: DbDependency,
    candidate_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    documents, total = documents_service.list_documents(
        db,
        organization_id=active_organization.id,
        candidate_id=candidate_id,
        limit=limit,
        offset=offset,
    )
    return DocumentListResponse(items=documents, total=total, limit=limit, offset=offset)


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    _origin: OriginChecked,
    file: Annotated[UploadFile, File()],
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
    candidate_id_form: Annotated[str | None, Form(alias="candidate_id")] = None,
    candidate_id_query: Annotated[str | None, Query(alias="candidate_id")] = None,
) -> Document | JSONResponse:
    raw_candidate_id = candidate_id_form or candidate_id_query
    if not raw_candidate_id:
        return _validation_error(request, "invalid_candidate_id")
    try:
        candidate_id = uuid.UUID(raw_candidate_id)
    except ValueError:
        return _validation_error(request, "invalid_candidate_id")

    # Un solo read acotado: nunca se carga un archivo arbitrariamente grande en memoria.
    data = await file.read(MAX_SIZE_BYTES + 1)
    try:
        return documents_service.create_document(
            db,
            organization_id=active_organization.id,
            candidate_id=candidate_id,
            uploader_id=actor.id,
            filename=file.filename or "",
            content_type=file.content_type or "",
            data=data,
        )
    except UploadValidationError as exc:
        return _validation_error(request, exc.code.value)
    except documents_service.DocumentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE) from None


# Registrada antes de /{document_id}: si no, "files" se interpretaría como UUID.
@router.get("/files/{token}")
def download_document_file(
    token: str,
    active_organization: CurrentOrganization,
    actor: CurrentUser,
    db: DbDependency,
) -> FileResponse:
    document_id = tokens.verify_download_token(token, organization_id=active_organization.id)
    if document_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Enlace de descarga no válido.")
    try:
        document, path = documents_service.prepare_download(
            db,
            organization_id=active_organization.id,
            document_id=document_id,
            actor_id=actor.id,
        )
        return FileResponse(
            path,
            media_type=document.content_type,
            filename=document.original_filename,
        )
    except documents_service.DocumentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE) from None
    except (OSError, RuntimeError):
        # FileResponse calcula metadata del archivo: nunca propagar la ruta al cliente.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE) from None


@router.post("/{document_id}/extract", status_code=status.HTTP_202_ACCEPTED)
def extract_document(
    _origin: OriginChecked,
    document_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> dict[str, object]:
    """Encola la extracción y devuelve metadatos; el estado se consulta por GET."""
    try:
        return documents_service.start_extraction(
            db,
            active_organization.id,
            document_id,
            actor.id,
        )
    except documents_service.DocumentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE) from None
    except documents_service.DocumentsDomainError as exc:
        if exc.code == "forbidden":
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Rol insuficiente.") from None
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Estado de documento inválido."
        ) from None


@router.get("/{document_id}/extraction", response_model=ExtractionResponse)
def get_extraction(
    document_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> ExtractionResponse:
    """Devuelve campos y evidencia acotada; nunca páginas completas del CV."""
    try:
        return documents_service.list_extraction_fields(
            db, organization_id=active_organization.id, document_id=document_id
        )
    except documents_service.DocumentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE) from None


@router.post(
    "/{document_id}/extraction/fields/{field_id}/confirm",
    response_model=ReviewResponse,
)
def confirm_extraction_field(
    _origin: OriginChecked,
    document_id: uuid.UUID,
    field_id: uuid.UUID,
    payload: ReviewRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> ReviewResponse:
    """Confirmación humana explícita; la API vuelve a verificar rol y tenant."""
    try:
        field = documents_service.confirm_field(
            db,
            organization_id=active_organization.id,
            document_id=document_id,
            field_id=field_id,
            actor_id=actor.id,
            value=payload.value,
        )
    except documents_service.DocumentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE) from None
    except documents_service.DocumentsDomainError as exc:
        raise _review_error(exc) from None
    return documents_service.review_response(field)


@router.post(
    "/{document_id}/extraction/confirm-all",
    response_model=ReviewSummaryResponse,
)
def confirm_extraction_all(
    _origin: OriginChecked,
    document_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> ReviewSummaryResponse:
    """Confirma solo evidencia válida; dudosos e inyección exigen revisión individual."""
    try:
        return documents_service.confirm_all(
            db,
            organization_id=active_organization.id,
            document_id=document_id,
            actor_id=actor.id,
        )
    except documents_service.DocumentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE) from None
    except documents_service.DocumentsDomainError as exc:
        raise _review_error(exc) from None


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> Document:
    try:
        return documents_service.get_document(
            db, organization_id=active_organization.id, document_id=document_id
        )
    except documents_service.DocumentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE) from None


@router.get("/{document_id}/download", response_model=DownloadUrlResponse)
def get_download_url(
    document_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> DownloadUrlResponse:
    try:
        document = documents_service.get_document(
            db, organization_id=active_organization.id, document_id=document_id
        )
    except documents_service.DocumentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE) from None
    return documents_service.issue_download_url(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    _origin: OriginChecked,
    document_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> None:
    try:
        documents_service.delete_document(
            db,
            organization_id=active_organization.id,
            document_id=document_id,
            actor_id=actor.id,
        )
    except documents_service.DocumentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE) from None
