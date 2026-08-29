from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.exceptions import ResourceNotFoundError, VectorIndexingError
from app.models.schemas import CandidateCreate, CandidateResponse
from app.services import candidate_service

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post("/", response_model=CandidateResponse, status_code=201)
def create_candidate(
    payload: CandidateCreate,
    tenant_id: UUID = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    try:
        return candidate_service.create_candidate(db, tenant_id, payload)
    except VectorIndexingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/upload", response_model=CandidateResponse, status_code=202)
def upload_resume(
    file: UploadFile = File(...),
    tenant_id: UUID = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    """Returns immediately with a `pending` candidate - no LLM call in this
    request. Poll GET /candidates/{id} for `status` to see when parsing
    (done asynchronously by app.worker) has finished."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = file.file.read()
    return candidate_service.enqueue_resume_upload(db, tenant_id, file_bytes)


@router.get("/", response_model=list[CandidateResponse])
def list_candidates(tenant_id: UUID = Depends(require_api_key), db: Session = Depends(get_db)):
    return candidate_service.list_candidates(db, tenant_id)


@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate(
    candidate_id: UUID,
    tenant_id: UUID = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    try:
        return candidate_service.get_candidate(db, tenant_id, candidate_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
