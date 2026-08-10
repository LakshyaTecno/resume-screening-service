class ServiceError(Exception):
    """Base exception for application-service failures."""


class ResourceNotFoundError(ServiceError):
    """Raised when a requested database resource does not exist."""


class ResumeContentError(ServiceError):
    """Raised when an uploaded resume has no usable text."""


class ResumeParserUnavailableError(ServiceError):
    """Raised when the configured LLM cannot parse a resume."""


class VectorIndexingError(ServiceError):
    """Raised when an entity cannot be indexed in the vector database."""
