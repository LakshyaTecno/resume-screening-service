from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ExperienceEntry(BaseModel):
    title: str
    company: str
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class EducationEntry(BaseModel):
    degree: str
    institution: str
    graduation_year: str | None = None


class ParsedResume(BaseModel):
    """Structured resume output from LLM parsing."""

    full_name: str = Field(description="Candidate's full name")
    email: EmailStr | None = Field(default=None, description="Contact email")
    phone: str | None = Field(default=None, description="Contact phone number")
    summary: str | None = Field(default=None, description="Professional summary")
    skills: list[str] = Field(default_factory=list, description="Technical and soft skills")
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)


class CandidateCreate(BaseModel):
    full_name: str
    email: str | None = None
    phone: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    raw_text: str | None = None


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str | None
    phone: str | None
    summary: str | None
    skills: list
    experience: list
    education: list
    created_at: datetime


class JobCreate(BaseModel):
    title: str
    company: str | None = None
    description: str
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    company: str | None
    description: str
    required_skills: list
    preferred_skills: list
    created_at: datetime


class MatchExplanation(BaseModel):
    """LLM-generated match explanation."""

    score: float = Field(ge=0, le=100, description="Match score from 0-100")
    strengths: list[str] = Field(description="Candidate strengths for this role")
    gaps: list[str] = Field(description="Skill or experience gaps")
    summary: str = Field(description="Brief match summary")


class RankedCandidate(BaseModel):
    candidate_id: UUID
    full_name: str
    vector_score: float
    llm_score: float
    rank: int
    explanation: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ScreeningRequest(BaseModel):
    job_id: UUID
    top_k: int | None = None
    top_n: int | None = None


class ScreeningResponse(BaseModel):
    job_id: UUID
    job_title: str
    total_candidates_screened: int
    ranked_candidates: list[RankedCandidate]
