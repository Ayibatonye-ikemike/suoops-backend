"""Common dependencies for inventory routes."""
from typing import Annotated, TypeAlias

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes_auth import get_current_user_id
from app.db.session import get_db
from app.services.inventory import build_inventory_service, InventoryService
from app.utils.feature_gate import FeatureGate

CurrentUserDep: TypeAlias = Annotated[int, Depends(get_current_user_id)]
DbDep: TypeAlias = Annotated[Session, Depends(get_db)]


def require_inventory_access(current_user_id: CurrentUserDep, db: DbDep) -> int:
    """
    Verify user has access to inventory features (Pro or Business plan).
    
    Raises HTTPException 403 if user doesn't have required plan.
    Returns the user_id if access is granted.
    """
    gate = FeatureGate(db, current_user_id)
    if not gate.user.plan.features.get("inventory", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "feature_gated",
                "message": "Inventory Management requires Pro plan or higher",
                "required_plan": "PRO",
                "current_plan": gate.user.plan.value,
                "upgrade_url": "/settings/subscription"
            }
        )
    return current_user_id


InventoryAccessDep: TypeAlias = Annotated[int, Depends(require_inventory_access)]


def require_inventory_admin(current_user_id: InventoryAccessDep, db: DbDep) -> int:
    """
    Verify user is admin/owner for inventory write operations.
    
    Solo users (no team) have full access.
    Team admins have full access.
    Team members can only read, not write.
    
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
                "message": "Only team admins can modify inventory",
                "required_role": "admin",
                "current_role": "member",
            }
        )
    
    # Solo user (no team) has full access
    return current_user_id


InventoryAdminDep: TypeAlias = Annotated[int, Depends(require_inventory_admin)]


def get_inventory_service(current_user_id: InventoryAccessDep, db: DbDep) -> InventoryService:
    """Get InventoryService for user with verified Pro/Business access (read)."""
    return build_inventory_service(db, user_id=current_user_id)


def get_inventory_service_admin(current_user_id: InventoryAdminDep, db: DbDep) -> InventoryService:
    """Get InventoryService for user with verified admin access (write)."""
    return build_inventory_service(db, user_id=current_user_id)


InventoryServiceDep: TypeAlias = Annotated[InventoryService, Depends(get_inventory_service)]
InventoryServiceAdminDep: TypeAlias = Annotated[InventoryService, Depends(get_inventory_service_admin)]
