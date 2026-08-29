from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db import Candidate, Job, MatchResult
from app.models.schemas import MatchExplanation, RankedCandidate, ScreeningResponse
from app.repositories import candidate_repository
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
    tenant_id: UUID,
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
    vector_matches = vector_store.query_similar_candidates(
        job_text, namespace=str(tenant_id), top_k=top_k
    )

    ranked: list[RankedCandidate] = []

    # Resolve candidates first, sequentially - this is a fast DB read, and
    # keeps the one SQLAlchemy session single-threaded (sessions aren't
    # thread-safe, so all DB reads stay on the main thread).
    resolved: list[tuple[Candidate, float]] = []
    for match in vector_matches:
        candidate_id = match.get("candidate_id")
        if not candidate_id:
            continue

        # tenant_id filter is defense in depth: even if the Pinecone
        # namespace above were ever misconfigured, this can't resolve a
        # different tenant's candidate row.
        candidate = candidate_repository.get_by_id(db, tenant_id, UUID(candidate_id))
        if not candidate:
            continue

        resolved.append((candidate, match["vector_score"]))

    def _evaluate(candidate: Candidate) -> MatchExplanation:
        return generate_match_explanation(
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

    # The LLM call per candidate is the slow part - a full local-model
    # generation each - and touches no DB session, so it's safe to fire
    # concurrently. This is what actually cuts wall-clock latency: these
    # used to be issued one at a time, so ranking a top_k=20 shortlist
    # meant 20 sequential model generations before a response went out.
    # Ollama itself must also be configured to actually process requests
    # in parallel (OLLAMA_NUM_PARALLEL) or it just queues them - see
    # settings.ranking_concurrency and the README note next to it.
    if resolved:
        with ThreadPoolExecutor(max_workers=settings.ranking_concurrency) as pool:
            explanations = list(pool.map(_evaluate, [candidate for candidate, _ in resolved]))
    else:
        explanations = []

    llm_evaluations: list[tuple[Candidate, float, MatchExplanation]] = [
        (candidate, vector_score, explanation)
        for (candidate, vector_score), explanation in zip(resolved, explanations)
    ]

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
