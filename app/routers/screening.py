from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import ResourceNotFoundError
from app.models.schemas import ScreeningRequest, ScreeningResponse
from app.services import job_service
from app.services.ranking import rank_candidates_for_job

router = APIRouter(prefix="/screening", tags=["screening"])


@router.post("/rank", response_model=ScreeningResponse)
def rank_candidates(payload: ScreeningRequest, db: Session = Depends(get_db)):
    try:
        job = job_service.get_job(db, payload.job_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return rank_candidates_for_job(
        db=db,
        job=job,
        top_k=payload.top_k,
        top_n=payload.top_n,
    )


@router.post("/rank/{job_id}", response_model=ScreeningResponse)
def rank_candidates_by_id(
    job_id: UUID,
    top_k: int | None = None,
    top_n: int | None = None,
    db: Session = Depends(get_db),
):
    try:
        job = job_service.get_job(db, job_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return rank_candidates_for_job(db=db, job=job, top_k=top_k, top_n=top_n)
