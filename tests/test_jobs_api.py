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
