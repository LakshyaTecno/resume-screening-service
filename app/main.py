from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import get_settings
from app.routers import admin, auth, billing, candidates, jobs, screening

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "AI microservice for resume parsing, candidate-job matching, and resume ranking. "
        "Uses LangChain + Ollama for local LLM inference and Pinecone for vector search."
    ),
    version="0.1.0",
)

# frontend/ runs on a different origin (localhost:3000) than the API
# (localhost:8000) - without this, every browser fetch() call from it
# fails at the CORS preflight before ever reaching a route.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exposes GET /metrics: request count, latency, in-progress requests, all
# broken down by path and status code - standard HTTP metrics, no
# hand-rolled middleware needed.
Instrumentator().instrument(app).expose(app)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(candidates.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(screening.router, prefix="/api/v1")
app.include_router(billing.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": settings.app_name}
