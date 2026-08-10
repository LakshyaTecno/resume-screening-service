from uuid import UUID

from sqlalchemy.orm import Session

from app.exceptions import ResourceNotFoundError, VectorIndexingError
from app.models.db import Job
from app.models.schemas import JobCreate
from app.repositories import job_repository
from app.services.embeddings import vector_store
from app.services.ranking import build_job_embed_text


def create_job(db: Session, payload: JobCreate) -> Job:
    job = Job(
        title=payload.title,
        company=payload.company,
        description=payload.description,
        required_skills=payload.required_skills,
        preferred_skills=payload.preferred_skills,
    )

    try:
        job_repository.add(db, job)
        job.pinecone_id = vector_store.upsert_job(
            job_id=str(job.id),
            text=build_job_embed_text(job),
            metadata={"title": job.title, "company": job.company or ""},
        )
        db.commit()
        db.refresh(job)
        return job
    except Exception as exc:
        db.rollback()
        raise VectorIndexingError(
            "Job could not be indexed. Check Ollama and Pinecone configuration."
        ) from exc


def list_jobs(db: Session) -> list[Job]:
    return job_repository.list_all(db)


def get_job(db: Session, job_id: UUID) -> Job:
    job = job_repository.get_by_id(db, job_id)
    if job is None:
        raise ResourceNotFoundError("Job not found")
    return job
