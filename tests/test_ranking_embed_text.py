from app.models.db import Candidate, Job
from app.services.ranking import build_candidate_embed_text, build_job_embed_text


def test_build_candidate_embed_text_happy_path():
    candidate = Candidate(
        full_name="Jane Doe",
        summary="Backend engineer",
        skills=["Python", "SQL"],
        experience=[{"title": "Engineer", "company": "Acme", "description": "Built APIs"}],
        education=[{"degree": "B.S. CS", "institution": "State University"}],
    )

    text = build_candidate_embed_text(candidate)

    assert "Name: Jane Doe" in text
    assert "Summary: Backend engineer" in text
    assert "Skills: Python, SQL" in text
    assert "Experience: Engineer at Acme - Built APIs" in text
    assert "Education: B.S. CS from State University" in text


def test_build_job_embed_text_happy_path():
    job = Job(
        title="Backend Engineer",
        company="Acme Corp",
        description="Build and maintain backend services.",
        required_skills=["Python", "SQL"],
        preferred_skills=["FastAPI"],
    )

    text = build_job_embed_text(job)

    assert "Title: Backend Engineer" in text
    assert "Company: Acme Corp" in text
    assert "Description: Build and maintain backend services." in text
    assert "Required Skills: Python, SQL" in text
    assert "Preferred Skills: FastAPI" in text
