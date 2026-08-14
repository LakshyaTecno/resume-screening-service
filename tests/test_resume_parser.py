import pytest

from app.services import resume_parser
from tests.factories import FakeEmptyPdfReader, FakePdfReader, FakeStructuredLLM, make_parsed_resume


def test_extract_text_from_pdf_happy_path(monkeypatch):
    monkeypatch.setattr(resume_parser, "PdfReader", FakePdfReader)

    text = resume_parser.extract_text_from_pdf(b"%PDF-1.4 fake bytes")

    assert text == "Jane Doe\nSoftware Engineer\nPython, SQL"


def test_parse_resume_text_happy_path(monkeypatch):
    parsed = make_parsed_resume(full_name="Jane Doe")
    monkeypatch.setattr(resume_parser, "get_llm", lambda: FakeStructuredLLM(parsed))

    result = resume_parser.parse_resume_text("Jane Doe resume text")

    assert result.full_name == "Jane Doe"
    assert "Python" in result.skills


def test_parse_resume_pdf_happy_path(monkeypatch):
    parsed = make_parsed_resume(full_name="Jane Doe")
    monkeypatch.setattr(resume_parser, "PdfReader", FakePdfReader)
    monkeypatch.setattr(resume_parser, "get_llm", lambda: FakeStructuredLLM(parsed))

    result, raw_text = resume_parser.parse_resume_pdf(b"%PDF-1.4 fake bytes")

    assert result.full_name == "Jane Doe"
    assert raw_text == "Jane Doe\nSoftware Engineer\nPython, SQL"


def test_parse_resume_pdf_blank_pdf_raises_value_error(monkeypatch):
    """A scanned/blank PDF extracts no text - this must fail loudly rather
    than silently hand an empty string to the LLM."""
    monkeypatch.setattr(resume_parser, "PdfReader", FakeEmptyPdfReader)

    with pytest.raises(ValueError, match="Could not extract text"):
        resume_parser.parse_resume_pdf(b"%PDF-1.4 fake bytes")
