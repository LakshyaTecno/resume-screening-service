from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import (
    ResourceNotFoundError,
    ResumeContentError,
    ResumeParserUnavailableError,
    VectorIndexingError,
)
from app.models.schemas import CandidateCreate, CandidateResponse
from app.services import candidate_service

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post("/", response_model=CandidateResponse, status_code=201)
def create_candidate(payload: CandidateCreate, db: Session = Depends(get_db)):
    try:
        return candidate_service.create_candidate(db, payload)
    except VectorIndexingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/upload", response_model=CandidateResponse, status_code=201)
def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = file.file.read()
    try:
        return candidate_service.create_candidate_from_pdf(db, file_bytes)
    except ResumeContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ResumeParserUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except VectorIndexingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/", response_model=list[CandidateResponse])
def list_candidates(db: Session = Depends(get_db)):
    return candidate_service.list_candidates(db)


@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate(candidate_id: UUID, db: Session = Depends(get_db)):
    try:
        return candidate_service.get_candidate(db, candidate_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
