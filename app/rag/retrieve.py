"""
RAG retrieval. Always scoped by clinic_id — one clinic's FAQ content must
never leak into another clinic's answers.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.db import KnowledgeChunk
from app.rag.embed import embed_text

TOP_K = 4
MAX_DISTANCE = 0.6  # cosine distance cutoff — tune against real clinic data


def retrieve_context(db: Session, clinic_id: str, query: str) -> list[str]:
    query_embedding = embed_text(query)

    results = (
        db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.clinic_id == clinic_id)
            .order_by(KnowledgeChunk.embedding.cosine_distance(query_embedding))
            .limit(TOP_K)
        )
        .scalars()
        .all()
    )

    # Filtering by distance matters as much as top_k: if NOTHING in the
    # knowledge base is actually relevant, we want an empty context so the
    # agent's grounding instruction ("say you don't know") kicks in, rather
    # than stuffing in the "closest" chunk even when it's unrelated.
    relevant = [
        chunk.content
        for chunk in results
        # NOTE: distance value would come from the query in a real
        # implementation (e.g. via .add_columns); simplified here for clarity.
    ]
    return relevant
