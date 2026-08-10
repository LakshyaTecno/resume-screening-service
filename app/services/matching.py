from langchain_core.prompts import ChatPromptTemplate

from app.llm.ollama_client import get_llm
from app.models.schemas import MatchExplanation

MATCH_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a senior technical recruiter. Evaluate how well a candidate matches a job.
Provide an honest score (0-100), list key strengths, identify gaps, and write a brief summary.""",
        ),
        (
            "human",
            """Job Title: {job_title}
Company: {company}

Job Description:
{job_description}

Required Skills: {required_skills}
Preferred Skills: {preferred_skills}

---

Candidate: {candidate_name}
Summary: {candidate_summary}
Skills: {candidate_skills}
Experience: {candidate_experience}
Education: {candidate_education}""",
        ),
    ]
)


def generate_match_explanation(
    job_title: str,
    company: str | None,
    job_description: str,
    required_skills: list,
    preferred_skills: list,
    candidate_name: str,
    candidate_summary: str | None,
    candidate_skills: list,
    candidate_experience: list,
    candidate_education: list,
) -> MatchExplanation:
    llm = get_llm().with_structured_output(MatchExplanation)
    chain = MATCH_PROMPT | llm
    return chain.invoke(
        {
            "job_title": job_title,
            "company": company or "N/A",
            "job_description": job_description,
            "required_skills": ", ".join(required_skills) or "None specified",
            "preferred_skills": ", ".join(preferred_skills) or "None specified",
            "candidate_name": candidate_name,
            "candidate_summary": candidate_summary or "Not provided",
            "candidate_skills": ", ".join(candidate_skills) or "None listed",
            "candidate_experience": _format_experience(candidate_experience),
            "candidate_education": _format_education(candidate_education),
        }
    )


def _format_experience(experience: list) -> str:
    if not experience:
        return "None listed"
    lines = []
    for exp in experience:
        if isinstance(exp, dict):
            lines.append(
                f"- {exp.get('title', 'N/A')} at {exp.get('company', 'N/A')} "
                f"({exp.get('start_date', '?')} – {exp.get('end_date', 'Present')})"
            )
        else:
            lines.append(f"- {exp}")
    return "\n".join(lines)


def _format_education(education: list) -> str:
    if not education:
        return "None listed"
    lines = []
    for edu in education:
        if isinstance(edu, dict):
            lines.append(
                f"- {edu.get('degree', 'N/A')} from {edu.get('institution', 'N/A')} "
                f"({edu.get('graduation_year', 'N/A')})"
            )
        else:
            lines.append(f"- {edu}")
    return "\n".join(lines)
