from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.db import Job


def add(db: Session, job: Job) -> Job:
    db.add(job)
    db.flush()
    return job


def get_by_id(db: Session, job_id: UUID) -> Job | None:
    return db.scalar(select(Job).where(Job.id == job_id))


def list_all(db: Session) -> list[Job]:
    statement = select(Job).order_by(Job.created_at.desc())
    return list(db.scalars(statement).all())
