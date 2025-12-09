"""Team management service for multi-user account access."""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.models import User
from app.models.team_models import (
    Team,
    TeamInvitation,
    TeamMember,
    TeamRole,
    InvitationStatus,
    generate_invite_token,
    utcnow,
)
from app.models.team_schemas import (
    TeamCreate,
    TeamMemberOut,
    InvitationCreate,
    InvitationOut,
    TeamOut,
    TeamWithMembersOut,
    UserTeamRole,
    InvitationValidation,
)


class TeamService:
    """Service for managing teams and invitations."""
    
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self._user: User | None = None
    
    @property
    def user(self) -> User:
        """Get the current user, cached."""
        if self._user is None:
            self._user = self.db.get(User, self.user_id)
            if not self._user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
        return self._user
    
    # ========================================================================
    # Team Management
    # ========================================================================
    
    def get_or_create_team(self, name: str | None = None) -> Team:
        """Get user's team or create one if none exists."""
        team = self._get_owned_team()
        if team:
            return team
        
        # Create new team with user as admin
        team_name = name or self.user.business_name or f"{self.user.name}'s Team"
        team = Team(
            name=team_name,
            admin_user_id=self.user_id,
        )
        self.db.add(team)
        self.db.commit()
        self.db.refresh(team)
        return team
    
    def _get_owned_team(self) -> Team | None:
        """Get team where user is admin."""
        stmt = select(Team).where(Team.admin_user_id == self.user_id)
        return self.db.scalar(stmt)
    
    def _get_member_team(self) -> tuple[Team, TeamMember] | tuple[None, None]:
        """Get team where user is a member (not admin)."""
        stmt = (
            select(TeamMember)
            .options(joinedload(TeamMember.team))
            .where(TeamMember.user_id == self.user_id)
        )
        membership = self.db.scalar(stmt)
        if membership:
            return membership.team, membership
        return None, None
    
    def get_user_team_role(self) -> UserTeamRole:
        """Get user's role in their team (if any)."""
        # Check if user is admin of a team
        owned_team = self._get_owned_team()
        if owned_team:
            return UserTeamRole(
                has_team=True,
                is_admin=True,
                team_id=owned_team.id,
                role=TeamRole.ADMIN,
                can_access_settings=True,
                can_edit_inventory=True,
            )
        
        # Check if user is a member of a team
        member_team, membership = self._get_member_team()
        if member_team and membership:
            return UserTeamRole(
                has_team=True,
                is_admin=False,
                team_id=member_team.id,
                role=TeamRole.MEMBER,
                can_access_settings=False,  # Members cannot access settings
                can_edit_inventory=False,   # Members cannot edit inventory
            )
        
        # User has no team - they are their own admin
        return UserTeamRole(
            has_team=False,
            is_admin=True,  # Solo users have full access to their own account
            team_id=None,
            role=None,
            can_access_settings=True,
            can_edit_inventory=True,
        )
    
    def get_team_details(self) -> TeamWithMembersOut | None:
        """Get full team details including members."""
        # First check if user is admin of a team
        team = self._get_owned_team()
        is_admin = team is not None
        
        # If not admin, check if member
        if not team:
            team, _ = self._get_member_team()
        
        if not team:
            return None
        
        # Load team with relationships
        stmt = (
            select(Team)
            .options(
                joinedload(Team.members).joinedload(TeamMember.user),
                joinedload(Team.invitations),
                joinedload(Team.admin_user),
            )
            .where(Team.id == team.id)
        )
        team = self.db.scalar(stmt)
        if not team:
            return None
        
        # Build admin member info
        admin_out = TeamMemberOut(
            id=0,  # Admin isn't in TeamMember table
            user_id=team.admin_user.id,
            user_name=team.admin_user.name,
            user_email=team.admin_user.email,
            role=TeamRole.ADMIN,
            joined_at=team.created_at,
        )
        
        # Build member list
        members_out = [
            TeamMemberOut(
                id=m.id,
                user_id=m.user.id,
                user_name=m.user.name,
                user_email=m.user.email,
                role=TeamRole.MEMBER,
                joined_at=m.joined_at,
            )
            for m in team.members
        ]
        
        # Build pending invitations (only show to admin)
        pending_invitations = []
        if is_admin:
            pending_invitations = [
                InvitationOut(
                    id=inv.id,
                    email=inv.email,
                    status=InvitationStatus(inv.status.value),
                    created_at=inv.created_at,
                    expires_at=inv.expires_at,
                    is_expired=inv.is_expired,
                    is_valid=inv.is_valid,
                )
                for inv in team.invitations
                if inv.status == InvitationStatus.PENDING
            ]
        
        member_count = len(team.members)
        
        return TeamWithMembersOut(
            team=TeamOut(
                id=team.id,
                name=team.name,
                admin_user_id=team.admin_user_id,
                max_members=team.max_members,
                member_count=member_count,
                created_at=team.created_at,
            ),
            admin=admin_out,
            members=members_out,
            pending_invitations=pending_invitations,
            can_invite=member_count < team.max_members,
        )
    
    def update_team_name(self, name: str) -> Team:
        """Update team name (admin only)."""
        team = self._require_admin_access()
        team.name = name
        self.db.commit()
        self.db.refresh(team)
        return team
    
    # ========================================================================
    # Invitation Management
    # ========================================================================
    
    def create_invitation(self, data: InvitationCreate) -> TeamInvitation:
        """Create and send a team invitation (admin only)."""
        team = self._require_admin_access()
        
        # Check if team is at capacity
        if len(team.members) >= team.max_members:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Team has reached maximum of {team.max_members} members"
            )
        
        # Check if user is already a member
        existing_member = self.db.scalar(
            select(TeamMember)
            .join(User)
            .where(TeamMember.team_id == team.id, User.email == data.email)
        )
        if existing_member:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a team member"
            )
        
        # Check if admin is inviting themselves
        if data.email == self.user.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot invite yourself"
            )
        
        # Check if there's already a pending invitation
        existing_invitation = self.db.scalar(
            select(TeamInvitation).where(
                TeamInvitation.team_id == team.id,
                TeamInvitation.email == data.email,
                TeamInvitation.status == InvitationStatus.PENDING,
            )
        )
        if existing_invitation and existing_invitation.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pending invitation already exists for this email"
            )
        
        # Create new invitation
        invitation = TeamInvitation(
            team_id=team.id,
            email=data.email,
            token=generate_invite_token(),
            invited_by_user_id=self.user_id,
        )
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)
        
        # TODO: Send invitation email
        # self._send_invitation_email(invitation)
        
        return invitation
    
    def revoke_invitation(self, invitation_id: int) -> TeamInvitation:
        """Revoke a pending invitation (admin only)."""
        team = self._require_admin_access()
        
        invitation = self.db.get(TeamInvitation, invitation_id)
        if not invitation or invitation.team_id != team.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found"
            )
        
        if invitation.status != InvitationStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only revoke pending invitations"
            )
        
        invitation.status = InvitationStatus.REVOKED
        invitation.responded_at = utcnow()
        self.db.commit()
        self.db.refresh(invitation)
        return invitation
    
    def validate_invitation(self, token: str) -> InvitationValidation:
        """Validate an invitation token (public, for preview)."""
        invitation = self.db.scalar(
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
    
    def accept_invitation(self, token: str) -> TeamMember:
        """Accept an invitation and join the team."""
        invitation = self.db.scalar(
            select(TeamInvitation)
            .options(joinedload(TeamInvitation.team))
            .where(TeamInvitation.token == token)
        )
        
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid invitation"
            )
        
        if not invitation.is_valid:
            error = "expired" if invitation.is_expired else invitation.status.value
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invitation is {error}"
            )
        
        # Verify the current user's email matches invitation
        if self.user.email != invitation.email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This invitation was sent to a different email address"
            )
        
        # Check if user is already in another team
        existing_team, _ = self._get_member_team()
        if existing_team:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already a member of another team"
            )
        
        # Check if user owns a team (admins can't join other teams)
        owned_team = self._get_owned_team()
        if owned_team:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You own a team and cannot join another team"
            )
        
        # Check team capacity
        team = invitation.team
        if len(team.members) >= team.max_members:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Team has reached maximum capacity"
            )
        
        # Create team membership
        membership = TeamMember(
            team_id=team.id,
            user_id=self.user_id,
            role=TeamRole.MEMBER,
        )
        self.db.add(membership)
        
        # Update invitation status
        invitation.status = InvitationStatus.ACCEPTED
        invitation.responded_at = utcnow()
        
        self.db.commit()
        self.db.refresh(membership)
        return membership
    
    # ========================================================================
    # Member Management
    # ========================================================================
    
    def remove_member(self, user_id: int) -> None:
        """Remove a member from the team (admin only)."""
        team = self._require_admin_access()
        
        if user_id == team.admin_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the team admin"
            )
        
        membership = self.db.scalar(
            select(TeamMember).where(
                TeamMember.team_id == team.id,
                TeamMember.user_id == user_id,
            )
        )
        
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found in team"
            )
        
        self.db.delete(membership)
        self.db.commit()
    
    def leave_team(self) -> None:
        """Leave the current team (members only)."""
        team, membership = self._get_member_team()
        
        if not team or not membership:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are not a member of any team"
            )
        
        self.db.delete(membership)
        self.db.commit()
    
    # ========================================================================
    # Helpers
    # ========================================================================
    
    def _require_admin_access(self) -> Team:
        """Require user to be admin of a team, raise if not."""
        team = self._get_owned_team()
        if not team:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only team admins can perform this action"
            )
        return team


def get_team_service(
    db: Annotated[Session, Depends(get_db)],
    user_id: int,
) -> TeamService:
    """Factory function to create TeamService."""
    return TeamService(db, user_id)
