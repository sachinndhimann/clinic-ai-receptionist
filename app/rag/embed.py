"""
Embedding generation. Swap the implementation here if you move from
OpenAI's text-embedding-3-small to a self-hosted multilingual model
(e.g. multilingual-e5-large) for better Hindi/Punjabi coverage — nothing
else in the codebase needs to change since KnowledgeChunk.embedding
dimension is fixed at model-setup time (update the Vector(1536) dimension
in models/db.py if you switch to a different-dimension model).
"""

from openai import OpenAI

from app.config.settings import settings

_client = OpenAI(api_key=settings.openai_api_key)


def embed_text(text: str) -> list[float]:
    response = _client.embeddings.create(
        model=settings.embedding_model,
        input=text,
    )
    return response.data[0].embedding
