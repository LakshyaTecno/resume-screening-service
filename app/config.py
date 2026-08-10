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

    # Event-driven ingestion worker (app/worker.py)
    aws_region: str = "us-east-1"
    sqs_queue_url: str = ""
    s3_bucket_name: str = ""
    dynamodb_table_name: str = "resume-processing-status"


@lru_cache
def get_settings() -> Settings:
    return Settings()
