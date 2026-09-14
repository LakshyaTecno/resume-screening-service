class ServiceError(Exception):
    """Base exception for application-service failures."""


class ResourceNotFoundError(ServiceError):
    """Raised when a requested database resource does not exist."""


class ResourceConflictError(ServiceError):
    """Raised when a resource already exists (e.g. an email already registered)."""


class InvalidCredentialsError(ServiceError):
    """Raised on a failed login - wrong email/password, or an invalid/
    unverifiable Google ID token. Deliberately distinct from
    ResourceNotFoundError so routers map it to 401, not 404."""


class ResumeContentError(ServiceError):
    """Raised when an uploaded resume has no usable text."""


class ResumeParserUnavailableError(ServiceError):
    """Raised when the configured LLM cannot parse a resume."""


class VectorIndexingError(ServiceError):
    """Raised when an entity cannot be indexed in the vector database."""
