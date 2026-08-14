from app.services import candidate_service
from tests.factories import make_parsed_resume


def test_create_candidate_happy_path(client, mock_vector_store):
    payload = {
        "full_name": "Jane Doe",
        "email": "jane.doe@example.com",
        "phone": "555-0100",
        "summary": "Experienced backend engineer.",
        "skills": ["Python", "SQL"],
        "experience": [],
        "education": [],
        "raw_text": "Jane Doe resume text",
    }

    response = client.post("/api/v1/candidates/", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Jane Doe"
    assert body["email"] == "jane.doe@example.com"
    assert "id" in body


def test_upload_candidate_happy_path(client, mock_vector_store, monkeypatch):
    parsed = make_parsed_resume(full_name="Uploaded Candidate")
    monkeypatch.setattr(
        candidate_service, "parse_resume_pdf", lambda file_bytes: (parsed, "raw resume text")
    )

    response = client.post(
        "/api/v1/candidates/upload",
        files={"file": ("resume.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json()["full_name"] == "Uploaded Candidate"


def test_list_candidates_happy_path(client, mock_vector_store):
    client.post(
        "/api/v1/candidates/",
        json={"full_name": "Jane Doe", "skills": [], "experience": [], "education": []},
    )

    response = client.get("/api/v1/candidates/")

    assert response.status_code == 200
    names = [c["full_name"] for c in response.json()]
    assert "Jane Doe" in names


def test_get_candidate_happy_path(client, mock_vector_store):
    create_response = client.post(
        "/api/v1/candidates/",
        json={"full_name": "Jane Doe", "skills": [], "experience": [], "education": []},
    )
    candidate_id = create_response.json()["id"]

    response = client.get(f"/api/v1/candidates/{candidate_id}")

    assert response.status_code == 200
    assert response.json()["id"] == candidate_id
