from uuid import uuid4

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


def test_upload_candidate_rejects_non_pdf_content_type(client):
    response = client.post(
        "/api/v1/candidates/upload",
        files={"file": ("resume.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400


def test_upload_candidate_unparseable_resume_returns_422(client, mock_vector_store, monkeypatch):
    def raise_content_error(file_bytes):
        raise ValueError("Could not extract text from PDF.")

    monkeypatch.setattr(candidate_service, "parse_resume_pdf", raise_content_error)

    response = client.post(
        "/api/v1/candidates/upload",
        files={"file": ("resume.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
    )

    assert response.status_code == 422


def test_upload_candidate_llm_unavailable_returns_503(client, mock_vector_store, monkeypatch):
    def raise_llm_down(file_bytes):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(candidate_service, "parse_resume_pdf", raise_llm_down)

    response = client.post(
        "/api/v1/candidates/upload",
        files={"file": ("resume.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
    )

    assert response.status_code == 503


def test_create_candidate_vector_indexing_error_returns_502(client, mock_vector_store):
    def raise_pinecone_down(candidate_id, text, metadata):
        raise RuntimeError("Pinecone unreachable")

    mock_vector_store.upsert_candidate = raise_pinecone_down

    response = client.post(
        "/api/v1/candidates/",
        json={"full_name": "Jane Doe", "skills": [], "experience": [], "education": []},
    )

    assert response.status_code == 502


def test_get_candidate_not_found_returns_404(client):
    response = client.get(f"/api/v1/candidates/{uuid4()}")

    assert response.status_code == 404
