from uuid import UUID

from sqlalchemy.orm import Session

from app.exceptions import (
    ResourceNotFoundError,
    ResumeContentError,
    ResumeParserUnavailableError,
    VectorIndexingError,
)
from app.models.db import Candidate
from app.models.schemas import CandidateCreate
from app.repositories import candidate_repository
from app.services import ingestion
from app.services.embeddings import vector_store
from app.services.ranking import build_candidate_embed_text
from app.services.resume_parser import parse_resume_pdf


def create_candidate(db: Session, tenant_id: UUID, payload: CandidateCreate) -> Candidate:
    candidate = Candidate(
        tenant_id=tenant_id,
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        summary=payload.summary,
        skills=payload.skills,
        experience=[entry.model_dump() for entry in payload.experience],
        education=[entry.model_dump() for entry in payload.education],
        raw_text=payload.raw_text,
    )
    candidate_repository.add(db, candidate)
    return _index_candidate(db, tenant_id, candidate)


def enqueue_resume_upload(db: Session, tenant_id: UUID, file_bytes: bytes) -> Candidate:
    """Async upload path: create a placeholder row, hand the file off to
    S3+SQS, and return immediately - no LLM call in this request. Parsing
    happens later in app.worker's consumption of the message this
    publishes; the client polls GET /candidates/{id} for `status`."""
    candidate = Candidate(tenant_id=tenant_id, status="pending")
    candidate_repository.add(db, candidate)
    db.commit()
    db.refresh(candidate)

    ingestion.upload_resume_and_enqueue(
        candidate_id=candidate.id, tenant_id=tenant_id, file_bytes=file_bytes
    )
    return candidate


def process_pending_candidate(
    db: Session, tenant_id: UUID, candidate_id: UUID, file_bytes: bytes
) -> None:
    """Consumer side of the async upload path - called from app.worker.
    Updates the existing placeholder row in place rather than inserting a
    new one, since the row (and its id, already handed to the client for
    polling) was created at upload time."""
    candidate = candidate_repository.get_by_id(db, tenant_id, candidate_id)
    if candidate is None:
        raise ResourceNotFoundError("Candidate not found")

    candidate.status = "processing"
    db.commit()

    try:
        parsed, raw_text = parse_resume_pdf(file_bytes)
    except ValueError as exc:
        # Permanent failure - the file itself is bad. Safe to tell a
        # polling client now; nothing will retry this successfully.
        candidate.status = "failed"
        db.commit()
        raise ResumeContentError(str(exc)) from exc
    except Exception as exc:
        # Transient failure (e.g. Ollama down) - leave status as
        # "processing" rather than "failed". run()'s SQS loop will retry
        # this message, and marking it failed now would show a polling
        # client a false permanent failure mid-retry.
        raise ResumeParserUnavailableError(
            "Resume parser is unavailable. Confirm Ollama is running and "
            "OLLAMA_LLM_MODEL is installed."
        ) from exc

    candidate.full_name = parsed.full_name
    candidate.email = str(parsed.email) if parsed.email else None
    candidate.phone = parsed.phone
    candidate.summary = parsed.summary
    candidate.skills = parsed.skills
    candidate.experience = [entry.model_dump() for entry in parsed.experience]
    candidate.education = [entry.model_dump() for entry in parsed.education]
    candidate.raw_text = raw_text
    candidate.status = "processed"
    _index_candidate(db, tenant_id, candidate)


def list_candidates(db: Session, tenant_id: UUID) -> list[Candidate]:
    return candidate_repository.list_all(db, tenant_id)


def get_candidate(db: Session, tenant_id: UUID, candidate_id: UUID) -> Candidate:
    candidate = candidate_repository.get_by_id(db, tenant_id, candidate_id)
    if candidate is None:
        raise ResourceNotFoundError("Candidate not found")
    return candidate


def _index_candidate(db: Session, tenant_id: UUID, candidate: Candidate) -> Candidate:
    try:
        candidate.pinecone_id = vector_store.upsert_candidate(
            candidate_id=str(candidate.id),
            text=build_candidate_embed_text(candidate),
            metadata={"full_name": candidate.full_name or ""},
            namespace=str(tenant_id),
        )
        db.commit()
        db.refresh(candidate)
        return candidate
    except Exception as exc:
        db.rollback()
        raise VectorIndexingError(
            "Candidate could not be indexed. Check Ollama and Pinecone configuration."
        ) from exc
