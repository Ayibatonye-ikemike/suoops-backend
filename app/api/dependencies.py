"""Common dependencies for role-based access control."""
from typing import Annotated, TypeAlias

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db


CurrentUserDep: TypeAlias = Annotated[int, Depends(get_current_user_id)]
DbDep: TypeAlias = Annotated[Session, Depends(get_db)]


def require_admin_role(current_user_id: CurrentUserDep, db: DbDep) -> int:
    """
    Verify user has admin privileges (can modify settings).
    
    Access rules:
    - Solo users (no team) have full access to their account
    - Team admins have full access
    - Team members (invited users) have read-only access
    
    Raises HTTPException 403 if user is a team member (not admin).
    Returns the user_id if access is granted.
    """
    from app.models.team_models import Team, TeamMember
    
    # Check if user is admin of a team (they have full access)
    team = db.scalar(select(Team).where(Team.admin_user_id == current_user_id))
    if team:
        return current_user_id
    
    # Check if user is a member of a team (they have read-only access)
    membership = db.scalar(select(TeamMember).where(TeamMember.user_id == current_user_id))
    if membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "role_restricted",
                "message": "Only team admins can modify settings",
                "required_role": "admin",
                "current_role": "member",
            }
        )
    
    # Solo user (no team) has full access
    return current_user_id


AdminUserDep: TypeAlias = Annotated[int, Depends(require_admin_role)]
