from uuid import uuid4


def test_create_job_happy_path(client, mock_vector_store):
    payload = {
        "title": "Backend Engineer",
        "company": "Acme Corp",
        "description": "Build and maintain backend services.",
        "required_skills": ["Python", "SQL"],
        "preferred_skills": ["FastAPI"],
    }

    response = client.post("/api/v1/jobs/", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Backend Engineer"
    assert "id" in body


def test_list_jobs_happy_path(client, mock_vector_store):
    client.post(
        "/api/v1/jobs/",
        json={"title": "Backend Engineer", "description": "Build APIs."},
    )

    response = client.get("/api/v1/jobs/")

    assert response.status_code == 200
    titles = [j["title"] for j in response.json()]
    assert "Backend Engineer" in titles


def test_create_job_vector_indexing_error_returns_502(client, mock_vector_store):
    def raise_pinecone_down(job_id, text, metadata):
        raise RuntimeError("Pinecone unreachable")

    mock_vector_store.upsert_job = raise_pinecone_down

    response = client.post(
        "/api/v1/jobs/",
        json={"title": "Backend Engineer", "description": "Build APIs."},
    )

    assert response.status_code == 502


def test_get_job_not_found_returns_404(client):
    response = client.get(f"/api/v1/jobs/{uuid4()}")

    assert response.status_code == 404
