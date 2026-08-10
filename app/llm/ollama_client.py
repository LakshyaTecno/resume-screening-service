from langchain_ollama import ChatOllama, OllamaEmbeddings

from app.config import get_settings

settings = get_settings()


def get_llm() -> ChatOllama:
    return ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.ollama_llm_model,
        temperature=0,
        num_ctx=settings.ollama_num_ctx,
        num_predict=settings.ollama_num_predict,
    )


def get_embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embed_model,
    )
