from io import BytesIO
from unittest.mock import MagicMock

import pytest

import app.worker as worker
from app.exceptions import ResumeContentError
from app.models.db import Candidate
from tests.factories import FakeEmptyPdfReader, FakePdfReader, FakeStructuredLLM, make_parsed_resume


def test_process_message_happy_path(worker_session_local, monkeypatch, mock_vector_store):
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
            "candidate_id": "ext-candidate-123",
            "s3_bucket": "resumes-bucket",
            "s3_key": "uploads/frank.pdf",
        }
    )

    fake_table.update_item.assert_called_once()
    kwargs = fake_table.update_item.call_args.kwargs
    assert kwargs["Key"] == {"candidate_id": "ext-candidate-123"}
    assert kwargs["ExpressionAttributeValues"][":status"] == "ai-processed"

    session = worker_session_local()
    saved = session.query(Candidate).filter(Candidate.full_name == "Frank Example").first()
    assert saved is not None
    session.close()


def test_process_message_empty_resume_propagates_resume_content_error(
    worker_session_local, monkeypatch, mock_vector_store
):
    """_process_message itself doesn't catch anything - run()'s message
    loop does, deciding whether to delete or retry based on exception
    type. This locks in that a ResumeContentError actually reaches that
    boundary instead of being silently swallowed or turned into something
    else along the way."""
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
                "candidate_id": "ext-candidate-456",
                "s3_bucket": "resumes-bucket",
                "s3_key": "uploads/blank.pdf",
            }
        )

    # Failed before reaching _mark_status - no status should have been written.
    fake_table.update_item.assert_not_called()
