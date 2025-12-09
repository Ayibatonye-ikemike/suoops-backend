"""API routes for team management."""
from typing import Annotated, TypeAlias

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.models.models import User
from app.models.team_schemas import (
    InvitationCreate,
    InvitationOut,
    InvitationValidation,
    TeamCreate,
    TeamMemberOut,
    TeamMemberRemove,
    TeamOut,
    TeamUpdate,
    TeamWithMembersOut,
    UserTeamRole,
    InvitationAccept,
)
from app.models.team_models import InvitationStatus
from app.services.team_service import TeamService
from app.utils.feature_gate import FeatureGate

router = APIRouter(prefix="/team", tags=["team"])

CurrentUserDep: TypeAlias = Annotated[int, Depends(get_current_user_id)]
DbDep: TypeAlias = Annotated[Session, Depends(get_db)]


def require_team_feature(current_user_id: CurrentUserDep, db: DbDep) -> int:
    """
    Verify user has access to team features (Pro or Business plan).
    
    Raises HTTPException 403 if user doesn't have required plan.
    Returns the user_id if access is granted.
    """
    gate = FeatureGate(db, current_user_id)
    # Team management uses same gate as inventory (Pro+)
    if not gate.user.plan.features.get("inventory", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "feature_gated",
                "message": "Team Management requires Pro plan or higher",
                "required_plan": "PRO",
                "current_plan": gate.user.plan.value,
                "upgrade_url": "/settings/subscription"
            }
        )
    return current_user_id


TeamAccessDep: TypeAlias = Annotated[int, Depends(require_team_feature)]


def get_team_service_dep(current_user_id: TeamAccessDep, db: DbDep) -> TeamService:
    """Get TeamService for user with verified Pro/Business access."""
    return TeamService(db, current_user_id)


TeamServiceDep: TypeAlias = Annotated[TeamService, Depends(get_team_service_dep)]


# ============================================================================
# Team Role Check (no feature gate - for UI checks)
# ============================================================================

@router.get("/role", response_model=UserTeamRole)
def get_my_team_role(current_user_id: CurrentUserDep, db: DbDep):
    """
    Get current user's team role for UI permission checks.
    
    This endpoint is NOT feature-gated so the frontend can check
    if user is admin/member to show/hide UI elements.
    """
    service = TeamService(db, current_user_id)
    return service.get_user_team_role()


# ============================================================================
# Team Management (requires Pro/Business)
# ============================================================================

@router.get("", response_model=TeamWithMembersOut | None)
def get_team(service: TeamServiceDep):
    """Get current user's team details including members and invitations."""
    return service.get_team_details()


@router.post("", response_model=TeamOut)
def create_team(data: TeamCreate, service: TeamServiceDep):
    """Create a new team (user becomes admin)."""
    team = service.get_or_create_team(data.name)
    member_count = len(team.members) if team.members else 0
    return TeamOut(
        id=team.id,
        name=team.name,
        admin_user_id=team.admin_user_id,
        max_members=team.max_members,
        member_count=member_count,
        created_at=team.created_at,
    )


@router.patch("", response_model=TeamOut)
def update_team(data: TeamUpdate, service: TeamServiceDep):
    """Update team settings (admin only)."""
    if data.name:
        team = service.update_team_name(data.name)
        member_count = len(team.members) if team.members else 0
        return TeamOut(
            id=team.id,
            name=team.name,
            admin_user_id=team.admin_user_id,
            max_members=team.max_members,
            member_count=member_count,
            created_at=team.created_at,
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No update data provided"
    )


# ============================================================================
# Invitation Management
# ============================================================================

@router.post("/invitations", response_model=InvitationOut)
def send_invitation(data: InvitationCreate, service: TeamServiceDep):
    """Send a team invitation to an email address (admin only)."""
    invitation = service.create_invitation(data)
    return InvitationOut(
        id=invitation.id,
        email=invitation.email,
        status=InvitationStatus(invitation.status.value),
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        is_expired=invitation.is_expired,
        is_valid=invitation.is_valid,
    )


@router.delete("/invitations/{invitation_id}", response_model=InvitationOut)
def revoke_invitation(invitation_id: int, service: TeamServiceDep):
    """Revoke a pending invitation (admin only)."""
    invitation = service.revoke_invitation(invitation_id)
    return InvitationOut(
        id=invitation.id,
        email=invitation.email,
        status=InvitationStatus(invitation.status.value),
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        is_expired=invitation.is_expired,
        is_valid=invitation.is_valid,
    )


@router.get("/invitations/validate", response_model=InvitationValidation)
def validate_invitation_token(token: str, db: DbDep):
    """
    Validate an invitation token (public endpoint for preview).
    
    This doesn't require authentication so users can preview
    the invitation before signing up/logging in.
    """
    # Create service without user context for validation
    from app.models.team_models import TeamInvitation
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload
    
    invitation = db.scalar(
        select(TeamInvitation)
        .options(
            joinedload(TeamInvitation.team),
            joinedload(TeamInvitation.invited_by),
        )
        .where(TeamInvitation.token == token)
    )
    
    if not invitation:
        return InvitationValidation(
            valid=False,
            team_name=None,
            inviter_name=None,
            email=None,
            error="Invalid invitation link",
        )
    
    if invitation.status != InvitationStatus.PENDING:
        return InvitationValidation(
            valid=False,
            team_name=invitation.team.name,
            inviter_name=invitation.invited_by.name if invitation.invited_by else None,
            email=invitation.email,
            error=f"Invitation has been {invitation.status.value}",
        )
    
    if invitation.is_expired:
        return InvitationValidation(
            valid=False,
            team_name=invitation.team.name,
            inviter_name=invitation.invited_by.name if invitation.invited_by else None,
            email=invitation.email,
            error="Invitation has expired",
        )
    
    return InvitationValidation(
        valid=True,
        team_name=invitation.team.name,
        inviter_name=invitation.invited_by.name if invitation.invited_by else None,
        email=invitation.email,
        error=None,
    )


@router.post("/invitations/accept", response_model=TeamMemberOut)
def accept_invitation(data: InvitationAccept, current_user_id: CurrentUserDep, db: DbDep):
    """
    Accept an invitation and join the team.
    
    Note: This endpoint is NOT feature-gated because invited users
    might be on free plans - they join the admin's team.
    """
    service = TeamService(db, current_user_id)
    membership = service.accept_invitation(data.token)
    
    # Get user info for response
    user = db.get(User, membership.user_id)
    return TeamMemberOut(
        id=membership.id,
        user_id=membership.user_id,
        user_name=user.name if user else "Unknown",
        user_email=user.email if user else None,
        role=membership.role,
        joined_at=membership.joined_at,
    )


# ============================================================================
# Member Management
# ============================================================================

@router.delete("/members/{user_id}")
def remove_team_member(user_id: int, service: TeamServiceDep):
    """Remove a member from the team (admin only)."""
    service.remove_member(user_id)
    return {"detail": "Member removed from team"}


@router.post("/leave")
def leave_team(current_user_id: CurrentUserDep, db: DbDep):
    """
    Leave the current team (for members, not admins).
    
    Note: This endpoint is NOT feature-gated because members
    should always be able to leave.
    """
    service = TeamService(db, current_user_id)
    service.leave_team()
    return {"detail": "You have left the team"}
