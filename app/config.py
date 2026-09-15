from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Resume Screening Service"
    debug: bool = False

    database_url: str = "postgresql://postgres:postgres@127.0.0.1:5433/resume_screening"

    ollama_base_url: str = "http://127.0.0.1:11435"
    ollama_llm_model: str = "llama3.1"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_num_ctx: int = Field(default=2048, gt=0)
    ollama_num_predict: int = Field(default=512, gt=0)

    pinecone_api_key: str = ""
    pinecone_index_name: str = "resume-screening-nomic-768"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    vector_top_k: int = Field(default=20, gt=0)
    ranking_top_n: int = Field(default=5, gt=0)
    # How many candidates' LLM evaluations run concurrently per /screening/rank
    # call. Only helps if Ollama is actually configured to process that many
    # requests in parallel - see OLLAMA_NUM_PARALLEL in the README.
    ranking_concurrency: int = Field(default=5, gt=0)

    # Event-driven ingestion worker (app/worker.py)
    aws_region: str = "us-east-1"
    sqs_queue_url: str = ""
    s3_bucket_name: str = ""
    dynamodb_table_name: str = "resume-processing-status"
    worker_metrics_port: int = Field(default=9100, gt=0)

    # Razorpay billing (app/services/billing_service.py, app/routers/billing.py)
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Admin API (app/admin_auth.py, app/routers/admin.py) - HTTP Basic,
    # a single operator credential, not tenant API keys. Empty by default,
    # same fail-closed intent as require_api_key.
    admin_username: str = ""
    admin_password: str = ""

    # Self-service tenant auth (app/jwt_auth.py, app/routers/auth.py) -
    # sits alongside require_api_key, not instead of it. Empty secret
    # fails closed the same way admin_username/admin_password do.
    jwt_secret: str = ""
    jwt_expiry_minutes: int = Field(default=1440, gt=0)
    google_oauth_client_id: str = ""

    # Lifetime cap (not period-scoped) for a tenant with no active
    # subscription - see billing_guard.enforce_quota's free-tier branch.
    free_tier_resume_limit: int = Field(default=20, gt=0)

    # frontend/ (see app/main.py's CORSMiddleware) - comma-separated
    # origins allowed to call this API from a browser. Defaults to the
    # Next.js dev server's own default port, not "*" - a browser-facing
    # API needs an explicit allowlist, not a wildcard, once credentials
    # (the Authorization header) are involved.
    cors_allowed_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
