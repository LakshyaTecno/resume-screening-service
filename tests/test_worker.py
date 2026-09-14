from io import BytesIO
from unittest.mock import MagicMock

import pytest

import app.worker as worker
from app.exceptions import ResumeContentError
from app.models.db import Candidate, Tenant
from tests.factories import FakeEmptyPdfReader, FakePdfReader, FakeStructuredLLM, make_parsed_resume


def _seed_tenant(db_session) -> Tenant:
    tenant = Tenant(name="Worker Test Tenant")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def _seed_pending_candidate(db_session, tenant: Tenant) -> Candidate:
    """The worker updates an existing placeholder row in place - it no
    longer inserts a new one - so tests need a real pre-existing row with
    the id the SQS message will reference, matching what
    candidate_service.enqueue_resume_upload creates at upload time."""
    candidate = Candidate(tenant_id=tenant.id, status="pending")
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)
    return candidate


def test_process_message_happy_path(
    worker_session_local, db_session, monkeypatch, mock_vector_store
):
    tenant = _seed_tenant(db_session)
    candidate = _seed_pending_candidate(db_session, tenant)
    monkeypatch.setattr(worker, "SessionLocal", worker_session_local)

    parsed = make_parsed_resume(full_name="Frank Example")
    monkeypatch.setattr("app.services.resume_parser.PdfReader", FakePdfReader)
    monkeypatch.setattr("app.services.resume_parser.get_llm", lambda: FakeStructuredLLM(parsed))

    monkeypatch.setattr(
        worker.s3, "get_object", lambda Bucket, Key: {"Body": BytesIO(b"%PDF-1.4 fake")}
    )
    fake_table = MagicMock()
    monkeypatch.setattr(worker.dynamodb, "Table", lambda name: fake_table)

    worker._process_message(
        {
            "candidate_id": str(candidate.id),
            "tenant_id": str(tenant.id),
            "s3_bucket": "resumes-bucket",
            "s3_key": "uploads/frank.pdf",
        }
    )

    fake_table.update_item.assert_called_once()
    kwargs = fake_table.update_item.call_args.kwargs
    assert kwargs["Key"] == {"candidate_id": str(candidate.id)}
    assert kwargs["ExpressionAttributeValues"][":status"] == "ai-processed"

    session = worker_session_local()
    updated = session.query(Candidate).filter(Candidate.id == candidate.id).first()
    assert updated.full_name == "Frank Example"
    assert updated.status == "processed"
    session.close()


def test_process_message_empty_resume_propagates_resume_content_error(
    worker_session_local, db_session, monkeypatch, mock_vector_store
):
    """_process_message itself doesn't catch anything - run()'s message
    loop does, deciding whether to delete or retry based on exception
    type. This locks in that a ResumeContentError actually reaches that
    boundary instead of being silently swallowed or turned into something
    else along the way."""
    tenant = _seed_tenant(db_session)
    candidate = _seed_pending_candidate(db_session, tenant)
    monkeypatch.setattr(worker, "SessionLocal", worker_session_local)
    monkeypatch.setattr("app.services.resume_parser.PdfReader", FakeEmptyPdfReader)

    monkeypatch.setattr(
        worker.s3, "get_object", lambda Bucket, Key: {"Body": BytesIO(b"%PDF-1.4 fake")}
    )
    fake_table = MagicMock()
    monkeypatch.setattr(worker.dynamodb, "Table", lambda name: fake_table)

    with pytest.raises(ResumeContentError):
        worker._process_message(
            {
                "candidate_id": str(candidate.id),
                "tenant_id": str(tenant.id),
                "s3_bucket": "resumes-bucket",
                "s3_key": "uploads/blank.pdf",
            }
        )

    # Failed before reaching _mark_status - no status should have been written.
    fake_table.update_item.assert_not_called()

    session = worker_session_local()
    failed = session.query(Candidate).filter(Candidate.id == candidate.id).first()
    assert failed.status == "failed"
    session.close()
