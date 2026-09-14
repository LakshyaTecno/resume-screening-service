from uuid import uuid4

import pytest

from app.exceptions import ResourceNotFoundError, ResumeContentError, ResumeParserUnavailableError
from app.models.db import Candidate, Tenant
from app.services import candidate_service
from tests.factories import FakeEmptyPdfReader, FakePdfReader, FakeStructuredLLM, make_parsed_resume


def _seed_tenant(db_session) -> Tenant:
    tenant = Tenant(name="Upload Test Tenant")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def _seed_pending_candidate(db_session, tenant: Tenant) -> Candidate:
    candidate = Candidate(tenant_id=tenant.id, status="pending")
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)
    return candidate


def test_enqueue_resume_upload_creates_pending_candidate_and_calls_ingestion(
    db_session, monkeypatch
):
    tenant = _seed_tenant(db_session)
    calls = {}
    monkeypatch.setattr(
        candidate_service.ingestion,
        "upload_resume_and_enqueue",
        lambda candidate_id, tenant_id, file_bytes: calls.update(
            candidate_id=candidate_id, tenant_id=tenant_id, file_bytes=file_bytes
        ),
    )

    candidate = candidate_service.enqueue_resume_upload(db_session, tenant.id, b"%PDF-1.4 fake")

    assert candidate.status == "pending"
    assert candidate.full_name is None
    assert calls["candidate_id"] == candidate.id
    assert calls["tenant_id"] == tenant.id


def test_process_pending_candidate_happy_path_updates_row_in_place(
    db_session, mock_vector_store, monkeypatch
):
    tenant = _seed_tenant(db_session)
    candidate = _seed_pending_candidate(db_session, tenant)
    candidate_id = candidate.id

    parsed = make_parsed_resume(full_name="Frank Example")
    monkeypatch.setattr("app.services.resume_parser.PdfReader", FakePdfReader)
    monkeypatch.setattr("app.services.resume_parser.get_llm", lambda: FakeStructuredLLM(parsed))

    candidate_service.process_pending_candidate(
        db_session, tenant.id, candidate_id, b"%PDF-1.4 fake"
    )

    updated = candidate_service.get_candidate(db_session, tenant.id, candidate_id)
    assert updated.status == "processed"
    assert updated.full_name == "Frank Example"
    assert updated.id == candidate_id  # same row updated in place, not a new insert


def test_process_pending_candidate_permanent_failure_marks_failed(
    db_session, mock_vector_store, monkeypatch
):
    tenant = _seed_tenant(db_session)
    candidate = _seed_pending_candidate(db_session, tenant)

    monkeypatch.setattr("app.services.resume_parser.PdfReader", FakeEmptyPdfReader)

    with pytest.raises(ResumeContentError):
        candidate_service.process_pending_candidate(
            db_session, tenant.id, candidate.id, b"%PDF-1.4 fake"
        )

    failed = candidate_service.get_candidate(db_session, tenant.id, candidate.id)
    assert failed.status == "failed"


def test_process_pending_candidate_transient_failure_leaves_status_processing(
    db_session, monkeypatch
):
    """Ollama-down is transient - SQS will retry the message, so status
    should not flip to a false-permanent "failed" mid-retry."""
    tenant = _seed_tenant(db_session)
    candidate = _seed_pending_candidate(db_session, tenant)

    def raise_llm_down(file_bytes):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(candidate_service, "parse_resume_pdf", raise_llm_down)

    with pytest.raises(ResumeParserUnavailableError):
        candidate_service.process_pending_candidate(
            db_session, tenant.id, candidate.id, b"%PDF-1.4 fake"
        )

    still_processing = candidate_service.get_candidate(db_session, tenant.id, candidate.id)
    assert still_processing.status == "processing"


def test_process_pending_candidate_missing_row_raises_not_found(db_session):
    tenant = _seed_tenant(db_session)

    with pytest.raises(ResourceNotFoundError):
        candidate_service.process_pending_candidate(
            db_session, tenant.id, uuid4(), b"%PDF-1.4 fake"
        )
