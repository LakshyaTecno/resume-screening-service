from pinecone import Pinecone, ServerlessSpec

from app.config import get_settings
from app.llm.ollama_client import get_embeddings

settings = get_settings()


class VectorStore:
    """Pinecone vector store for resume and job embeddings."""

    def __init__(self) -> None:
        self._client: Pinecone | None = None
        self._index = None

    @property
    def client(self) -> Pinecone:
        if self._client is None:
            if not settings.pinecone_api_key:
                raise RuntimeError("PINECONE_API_KEY is not configured")
            self._client = Pinecone(api_key=settings.pinecone_api_key)
        return self._client

    @property
    def index(self):
        if self._index is None:
            self._ensure_index()
            self._index = self.client.Index(settings.pinecone_index_name)
        return self._index

    def _ensure_index(self) -> None:
        existing = [idx.name for idx in self.client.list_indexes()]
        if settings.pinecone_index_name not in existing:
            sample_embedding = get_embeddings().embed_query("dimension probe")
            self.client.create_index(
                name=settings.pinecone_index_name,
                dimension=len(sample_embedding),
                metric="cosine",
                spec=ServerlessSpec(cloud=settings.pinecone_cloud, region=settings.pinecone_region),
            )

    def embed_text(self, text: str) -> list[float]:
        return get_embeddings().embed_query(text)

    def upsert_candidate(self, candidate_id: str, text: str, metadata: dict) -> str:
        vector = self.embed_text(text)
        vector_id = f"candidate-{candidate_id}"
        self.index.upsert(
            vectors=[
                {
                    "id": vector_id,
                    "values": vector,
                    "metadata": {**metadata, "type": "candidate", "candidate_id": candidate_id},
                }
            ]
        )
        return vector_id

    def upsert_job(self, job_id: str, text: str, metadata: dict) -> str:
        vector = self.embed_text(text)
        vector_id = f"job-{job_id}"
        self.index.upsert(
            vectors=[
                {
                    "id": vector_id,
                    "values": vector,
                    "metadata": {**metadata, "type": "job", "job_id": job_id},
                }
            ]
        )
        return vector_id

    def query_similar_candidates(
        self, job_text: str, top_k: int = 20, job_id: str | None = None
    ) -> list[dict]:
        query_vector = self.embed_text(job_text)
        filter_dict = {"type": {"$eq": "candidate"}}
        results = self.index.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=True,
            filter=filter_dict,
        )
        matches = []
        for match in results.get("matches", []):
            metadata = match.get("metadata", {})
            matches.append(
                {
                    "candidate_id": metadata.get("candidate_id"),
                    "vector_score": match.get("score", 0.0),
                    "metadata": metadata,
                }
            )
        return matches


vector_store = VectorStore()
