from langchain_core.runnables import RunnableLambda

from app.models.schemas import (
    CandidateCreate,
    EducationEntry,
    ExperienceEntry,
    JobCreate,
    MatchExplanation,
    ParsedResume,
)


class FakeStructuredLLM:
    """Stand-in for get_llm()'s return value."""

    def __init__(self, output):
        self._output = output

    def with_structured_output(self, schema):
        return RunnableLambda(lambda _input: self._output)


class FakePdfPage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text


class FakePdfReader:
    """Stand-in for pypdf.PdfReader; ignores the stream, returns fixed pages."""

    def __init__(self, stream):
        self.pages = [FakePdfPage("Jane Doe\nSoftware Engineer\nPython, SQL")]


class FakeEmptyPdfReader:
    """Stand-in for a scanned/blank PDF - pages exist but extract no text."""

    def __init__(self, stream):
        self.pages = [FakePdfPage(""), FakePdfPage("")]


def make_parsed_resume(**overrides) -> ParsedResume:
    defaults = dict(
        full_name="Jane Doe",
        email="jane.doe@example.com",
        phone="555-0100",
        summary="Experienced backend engineer.",
        skills=["Python", "SQL", "FastAPI"],
        experience=[
            ExperienceEntry(
                title="Backend Engineer",
                company="Acme Corp",
                start_date="2020-01",
                end_date="Present",
                description="Built APIs.",
            )
        ],
        education=[
            EducationEntry(
                degree="B.S. Computer Science",
                institution="State University",
                graduation_year="2019",
            )
        ],
    )
    defaults.update(overrides)
    return ParsedResume(**defaults)


def make_match_explanation(**overrides) -> MatchExplanation:
    defaults = dict(
        score=87.5,
        strengths=["Strong Python background", "Relevant API experience"],
        gaps=["No Kubernetes experience mentioned"],
        summary="Strong match for the backend role.",
    )
    defaults.update(overrides)
    return MatchExplanation(**defaults)


def make_candidate_create(**overrides) -> CandidateCreate:
    defaults = dict(
        full_name="Jane Doe",
        email="jane.doe@example.com",
        phone="555-0100",
        summary="Experienced backend engineer.",
        skills=["Python", "SQL"],
        experience=[],
        education=[],
        raw_text="Jane Doe resume text",
    )
    defaults.update(overrides)
    return CandidateCreate(**defaults)


def make_job_create(**overrides) -> JobCreate:
    defaults = dict(
        title="Backend Engineer",
        company="Acme Corp",
        description="Build and maintain backend services.",
        required_skills=["Python", "SQL"],
        preferred_skills=["FastAPI"],
    )
    defaults.update(overrides)
    return JobCreate(**defaults)
