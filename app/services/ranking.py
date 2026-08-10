from uuid import UUID

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db import Candidate, Job, MatchResult
from app.models.schemas import MatchExplanation, RankedCandidate, ScreeningResponse
from app.services.embeddings import vector_store
from app.services.matching import generate_match_explanation

settings = get_settings()


def build_candidate_embed_text(candidate: Candidate) -> str:
    parts = [
        f"Name: {candidate.full_name}",
        f"Summary: {candidate.summary or ''}",
        f"Skills: {', '.join(candidate.skills or [])}",
    ]
    for exp in candidate.experience or []:
        if isinstance(exp, dict):
            parts.append(
                f"Experience: {exp.get('title')} at {exp.get('company')} - {exp.get('description', '')}"
            )
    for edu in candidate.education or []:
        if isinstance(edu, dict):
            parts.append(f"Education: {edu.get('degree')} from {edu.get('institution')}")
    return "\n".join(parts)


def build_job_embed_text(job: Job) -> str:
    return (
        f"Title: {job.title}\n"
        f"Company: {job.company or ''}\n"
        f"Description: {job.description}\n"
        f"Required Skills: {', '.join(job.required_skills or [])}\n"
        f"Preferred Skills: {', '.join(job.preferred_skills or [])}"
    )


def rank_candidates_for_job(
    db: Session,
    job: Job,
    top_k: int | None = None,
    top_n: int | None = None,
) -> ScreeningResponse:
    """
    Hybrid retrieval pipeline:
    1. Vector search narrows to top_k candidates (cosine similarity via Pinecone)
    2. LLM evaluates and ranks the shortlist to top_n
    """
    top_k = top_k or settings.vector_top_k
    top_n = top_n or settings.ranking_top_n

    job_text = build_job_embed_text(job)
    vector_matches = vector_store.query_similar_candidates(job_text, top_k=top_k)

    ranked: list[RankedCandidate] = []
    llm_evaluations: list[tuple[Candidate, float, MatchExplanation]] = []

    for match in vector_matches:
        candidate_id = match.get("candidate_id")
        if not candidate_id:
            continue

        candidate = db.query(Candidate).filter(Candidate.id == UUID(candidate_id)).first()
        if not candidate:
            continue

        explanation = generate_match_explanation(
            job_title=job.title,
            company=job.company,
            job_description=job.description,
            required_skills=job.required_skills or [],
            preferred_skills=job.preferred_skills or [],
            candidate_name=candidate.full_name,
            candidate_summary=candidate.summary,
            candidate_skills=candidate.skills or [],
            candidate_experience=candidate.experience or [],
            candidate_education=candidate.education or [],
        )

        llm_evaluations.append(
            (
                candidate,
                match["vector_score"],
                explanation,
            )
        )

    llm_evaluations.sort(key=lambda x: x[2].score, reverse=True)
    shortlist = llm_evaluations[:top_n]

    for rank, (candidate, vector_score, explanation) in enumerate(shortlist, start=1):
        ranked.append(
            RankedCandidate(
                candidate_id=candidate.id,
                full_name=candidate.full_name,
                vector_score=round(vector_score, 4),
                llm_score=explanation.score,
                rank=rank,
                explanation=explanation.summary,
                strengths=explanation.strengths,
                gaps=explanation.gaps,
            )
        )

        match_record = MatchResult(
            candidate_id=candidate.id,
            job_id=job.id,
            vector_score=vector_score,
            llm_score=explanation.score,
            rank=rank,
            explanation=explanation.summary,
        )
        db.add(match_record)

    db.commit()

    return ScreeningResponse(
        job_id=job.id,
        job_title=job.title,
        total_candidates_screened=len(vector_matches),
        ranked_candidates=ranked,
    )
