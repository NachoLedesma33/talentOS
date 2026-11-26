from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core import config
from app.db.session import get_db
from app.identity import service as identity_service
from app.identity.dependencies import (
    get_current_organization,
    get_current_user,
    require_roles,
    verify_origin,
)
from app.identity.models import Membership, MembershipRole, Organization, User
from app.identity.schemas import (
    InvitationAcceptResponse,
    InvitationCreateResponse,
    InvitationDetailResponse,
    MemberInvite,
    MemberResponse,
    MemberRoleUpdate,
    OrganizationCreate,
    OrganizationResponse,
)

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])

DbDependency = Annotated[DBSession, Depends(get_db)]
OriginChecked = Annotated[None, Depends(verify_origin)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentOrganization = Annotated[Organization, Depends(get_current_organization)]
ReadMember = Annotated[
    Membership,
    Depends(
        require_roles(
            MembershipRole.OWNER,
            MembershipRole.ADMIN,
            MembershipRole.REVIEWER,
            MembershipRole.VIEWER,
        )
    ),
]
WriteMember = Annotated[
    Membership, Depends(require_roles(MembershipRole.OWNER, MembershipRole.ADMIN))
]


# Rutas estáticas antes de `/{org_id}/...`: el token no es un UUID de organización.
@router.get("/invitations/{token}", response_model=InvitationDetailResponse)
def preview_invitation(token: str, db: DbDependency) -> InvitationDetailResponse:
    try:
        return identity_service.get_invitation_details(db, token=token)
    except identity_service.InvitationTokenError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitación no encontrada."
        ) from None


@router.post("/invitations/{token}/accept", response_model=InvitationAcceptResponse)
def accept_invitation(
    _origin: OriginChecked,
    token: str,
    current_user: CurrentUser,
    db: DbDependency,
) -> InvitationAcceptResponse:
    try:
        return identity_service.accept_invitation(db, token=token, user=current_user)
    except identity_service.InvitationTokenError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitación no encontrada."
        ) from None
    except identity_service.InvitationEmailMismatchError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La invitación corresponde a otro email.",
        ) from None
    except identity_service.MemberAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El usuario ya es miembro."
        ) from None


@router.get("/", response_model=list[OrganizationResponse])
def list_organizations(
    current_user: CurrentUser,
    db: DbDependency,
) -> list[Organization]:
    return identity_service.list_user_organizations(db, user_id=current_user.id)


@router.post("/", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(
    _origin: OriginChecked,
    payload: OrganizationCreate,
    current_user: CurrentUser,
    db: DbDependency,
) -> Organization:
    try:
        return identity_service.create_organization(
            db, creator=current_user, name=payload.name, slug=payload.slug
        )
    except identity_service.OrganizationSlugAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El slug ya está en uso."
        ) from None


@router.post(
    "/{org_id}/invitations",
    response_model=InvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    _origin: OriginChecked,
    org_id: uuid.UUID,
    payload: MemberInvite,
    active_organization: CurrentOrganization,
    current_user: CurrentUser,
    _member: WriteMember,
    db: DbDependency,
) -> InvitationCreateResponse:
    try:
        token = identity_service.create_invitation(
            db,
            actor=current_user,
            active_organization_id=active_organization.id,
            requested_organization_id=org_id,
            email=payload.email,
            role=payload.role,
        )
    except identity_service.OrganizationAccessError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada."
        ) from None
    except (
        identity_service.InsufficientRoleError,
        identity_service.RoleAssignmentForbiddenError,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Rol insuficiente."
        ) from None
    except identity_service.MemberAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El usuario ya es miembro."
        ) from None

    settings = config.get_settings()
    return InvitationCreateResponse(
        message="Invitación creada.",
        dev_token=token if settings.APP_ENV != "production" else None,
    )


@router.get("/{org_id}/members", response_model=list[MemberResponse])
def list_members(
    org_id: uuid.UUID,
    active_organization: CurrentOrganization,
    _member: ReadMember,
    db: DbDependency,
) -> list[MemberResponse]:
    try:
        return identity_service.list_members(
            db,
            active_organization_id=active_organization.id,
            requested_organization_id=org_id,
        )
    except identity_service.OrganizationAccessError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada."
        ) from None


@router.post(
    "/{org_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED
)
def invite_member(
    _origin: OriginChecked,
    org_id: uuid.UUID,
    payload: MemberInvite,
    active_organization: CurrentOrganization,
    current_user: CurrentUser,
    _member: WriteMember,
    db: DbDependency,
) -> MemberResponse:
    try:
        return identity_service.invite_member(
            db,
            actor=current_user,
            active_organization_id=active_organization.id,
            requested_organization_id=org_id,
            email=payload.email,
            role=payload.role,
        )
    except identity_service.OrganizationAccessError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada."
        ) from None
    except identity_service.InvitedUserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario invitado no encontrado."
        ) from None
    except identity_service.CannotInviteSelfError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="El actor ya es miembro."
        ) from None
    except (
        identity_service.InsufficientRoleError,
        identity_service.RoleAssignmentForbiddenError,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Rol insuficiente."
        ) from None
    except identity_service.MemberAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El usuario ya es miembro."
        ) from None


@router.patch("/{org_id}/members/{user_id}", response_model=MemberResponse)
def change_member_role(
    _origin: OriginChecked,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: MemberRoleUpdate,
    active_organization: CurrentOrganization,
    current_user: CurrentUser,
    _member: WriteMember,
    db: DbDependency,
) -> MemberResponse:
    try:
        return identity_service.change_member_role(
            db,
            actor=current_user,
            active_organization_id=active_organization.id,
            requested_organization_id=org_id,
            user_id=user_id,
            new_role=payload.role,
        )
    except identity_service.OrganizationAccessError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada."
        ) from None
    except identity_service.MemberNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Miembro no encontrado."
        ) from None
    except identity_service.RoleUnchangedError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="El rol no cambia."
        ) from None
    except (
        identity_service.InsufficientRoleError,
        identity_service.RoleAssignmentForbiddenError,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Rol insuficiente."
        ) from None
    except identity_service.LastOwnerError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="La organización debe conservar un owner."
        ) from None
