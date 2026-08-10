from uuid import UUID

from sqlalchemy.orm import Session

from app.exceptions import (
    ResourceNotFoundError,
    ResumeContentError,
    ResumeParserUnavailableError,
    VectorIndexingError,
)
from app.models.db import Candidate
from app.models.schemas import CandidateCreate, ParsedResume
from app.repositories import candidate_repository
from app.services.embeddings import vector_store
from app.services.ranking import build_candidate_embed_text
from app.services.resume_parser import parse_resume_pdf


def create_candidate(db: Session, payload: CandidateCreate) -> Candidate:
    candidate = Candidate(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        summary=payload.summary,
        skills=payload.skills,
        experience=[entry.model_dump() for entry in payload.experience],
        education=[entry.model_dump() for entry in payload.education],
        raw_text=payload.raw_text,
    )
    return _save_and_index(db, candidate)


def create_candidate_from_pdf(db: Session, file_bytes: bytes) -> Candidate:
    try:
        parsed, raw_text = parse_resume_pdf(file_bytes)
    except ValueError as exc:
        raise ResumeContentError(str(exc)) from exc
    except Exception as exc:
        raise ResumeParserUnavailableError(
            "Resume parser is unavailable. Confirm Ollama is running and "
            "OLLAMA_LLM_MODEL is installed."
        ) from exc

    candidate = _candidate_from_parsed_resume(parsed, raw_text)
    return _save_and_index(db, candidate)


def list_candidates(db: Session) -> list[Candidate]:
    return candidate_repository.list_all(db)


def get_candidate(db: Session, candidate_id: UUID) -> Candidate:
    candidate = candidate_repository.get_by_id(db, candidate_id)
    if candidate is None:
        raise ResourceNotFoundError("Candidate not found")
    return candidate


def _candidate_from_parsed_resume(parsed: ParsedResume, raw_text: str) -> Candidate:
    return Candidate(
        full_name=parsed.full_name,
        email=str(parsed.email) if parsed.email else None,
        phone=parsed.phone,
        summary=parsed.summary,
        skills=parsed.skills,
        experience=[entry.model_dump() for entry in parsed.experience],
        education=[entry.model_dump() for entry in parsed.education],
        raw_text=raw_text,
    )


def _save_and_index(db: Session, candidate: Candidate) -> Candidate:
    try:
        candidate_repository.add(db, candidate)
        candidate.pinecone_id = vector_store.upsert_candidate(
            candidate_id=str(candidate.id),
            text=build_candidate_embed_text(candidate),
            metadata={"full_name": candidate.full_name},
        )
        db.commit()
        db.refresh(candidate)
        return candidate
    except Exception as exc:
        db.rollback()
        raise VectorIndexingError(
            "Candidate could not be indexed. Check Ollama and Pinecone configuration."
        ) from exc
