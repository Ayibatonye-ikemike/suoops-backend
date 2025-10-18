from typing import Annotated, TypeAlias

from fastapi import APIRouter, Depends

from app.api.routes_auth import get_current_user_id
from app.models import schemas
from app.services.payroll_service import PayrollService, get_payroll_service

router = APIRouter()

CurrentUserDep: TypeAlias = Annotated[int, Depends(get_current_user_id)]
PayrollServiceDep: TypeAlias = Annotated[PayrollService, Depends(get_payroll_service)]


@router.get("/workers", response_model=list[schemas.WorkerOut])
def list_workers(
    current_user_id: CurrentUserDep,
    svc: PayrollServiceDep,
):
    """Get all workers for the current user."""
    return svc.get_workers(current_user_id)


@router.post("/workers", response_model=schemas.WorkerOut)
def add_worker(
    payload: schemas.WorkerCreate,
    current_user_id: CurrentUserDep,
    svc: PayrollServiceDep,
):
    return svc.add_worker(current_user_id, payload)


@router.post("/runs", response_model=schemas.PayrollRunOut)
def create_payroll_run(
    payload: schemas.PayrollRunCreate,
    current_user_id: CurrentUserDep,
    svc: PayrollServiceDep,
):
    return svc.create_payroll_run(current_user_id, payload)
