from app.models.db import Candidate
from app.services import ranking
from tests.factories import make_match_explanation


def _seed_candidate(db_session, full_name="Jane Doe") -> Candidate:
    candidate = Candidate(
        full_name=full_name,
        summary="Backend engineer",
        skills=["Python", "SQL"],
        experience=[],
        education=[],
    )
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)
    return candidate


def _create_job(client) -> str:
    response = client.post(
        "/api/v1/jobs/",
        json={"title": "Backend Engineer", "description": "Build APIs."},
    )
    return response.json()["id"]


def test_rank_candidates_happy_path(client, db_session, mock_vector_store, monkeypatch):
    candidate = _seed_candidate(db_session)
    job_id = _create_job(client)

    monkeypatch.setattr(
        ranking.vector_store,
        "query_similar_candidates",
        lambda job_text, top_k=20, job_id=None: [
            {"candidate_id": str(candidate.id), "vector_score": 0.92, "metadata": {}}
        ],
    )
    monkeypatch.setattr(
        ranking,
        "generate_match_explanation",
        lambda **kwargs: make_match_explanation(score=90.0),
    )

    response = client.post(
        "/api/v1/screening/rank",
        json={"job_id": job_id, "top_k": 5, "top_n": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_candidates_screened"] == 1
    assert len(body["ranked_candidates"]) == 1
    ranked = body["ranked_candidates"][0]
    assert ranked["full_name"] == "Jane Doe"
    assert ranked["llm_score"] == 90.0
    assert ranked["rank"] == 1


def test_rank_candidates_by_job_id_path_happy_path(
    client, db_session, mock_vector_store, monkeypatch
):
    candidate = _seed_candidate(db_session)
    job_id = _create_job(client)

    monkeypatch.setattr(
        ranking.vector_store,
        "query_similar_candidates",
        lambda job_text, top_k=20, job_id=None: [
            {"candidate_id": str(candidate.id), "vector_score": 0.8, "metadata": {}}
        ],
    )
    monkeypatch.setattr(
        ranking, "generate_match_explanation", lambda **kwargs: make_match_explanation()
    )

    response = client.post(f"/api/v1/screening/rank/{job_id}")

    assert response.status_code == 200
    assert response.json()["total_candidates_screened"] == 1
