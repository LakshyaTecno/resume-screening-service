from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.db import Candidate


def add(db: Session, candidate: Candidate) -> Candidate:
    db.add(candidate)
    db.flush()
    return candidate


def get_by_id(db: Session, candidate_id: UUID) -> Candidate | None:
    return db.scalar(select(Candidate).where(Candidate.id == candidate_id))


def list_all(db: Session) -> list[Candidate]:
    statement = select(Candidate).order_by(Candidate.created_at.desc())
    return list(db.scalars(statement).all())
