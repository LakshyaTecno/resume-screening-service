from io import BytesIO

from langchain_core.prompts import ChatPromptTemplate
from pypdf import PdfReader

from app.llm.ollama_client import get_llm
from app.models.schemas import ParsedResume

PARSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert resume parser. Extract structured information from the resume text.
Return accurate, concise data. If a field is not present, use null or an empty list.
For dates, use formats like "2020-01" or "Present".

Do not skip these fields when the source text contains them:
- summary: copy the professional summary paragraph if the resume has one.
- experience[].description: copy or tightly summarize the 1-2 sentences describing each job, if present.
These fields are commonly missed - double check the source text for them before leaving them null.""",
        ),
        ("human", "Parse the following resume:\n\n{resume_text}"),
    ]
)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def parse_resume_text(resume_text: str) -> ParsedResume:
    llm = get_llm().with_structured_output(ParsedResume)
    chain = PARSE_PROMPT | llm
    return chain.invoke({"resume_text": resume_text})


def parse_resume_pdf(file_bytes: bytes) -> tuple[ParsedResume, str]:
    raw_text = extract_text_from_pdf(file_bytes)
    if not raw_text:
        raise ValueError("Could not extract text from PDF. The file may be scanned or empty.")
    parsed = parse_resume_text(raw_text)
    return parsed, raw_text
