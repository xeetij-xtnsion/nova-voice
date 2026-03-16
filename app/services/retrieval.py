from typing import List, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import KBChunk
from app.config import settings
import logging

logger = logging.getLogger(__name__)


async def retrieve_with_confidence(
    query_embedding: List[float],
    session: AsyncSession,
    top_k: int = None,
    kb_version: int = None,
    similarity_threshold: float = None
) -> Dict:
    """Retrieve relevant chunks using vector similarity search with confidence scoring."""
    if top_k is None:
        top_k = settings.top_k
    if kb_version is None:
        kb_version = settings.kb_version
    if similarity_threshold is None:
        similarity_threshold = settings.similarity_threshold

    try:
        query = (
            select(
                KBChunk.chunk_id,
                KBChunk.source_file,
                KBChunk.section_heading,
                KBChunk.content,
                KBChunk.chunk_index,
                (1 - KBChunk.embedding.cosine_distance(query_embedding)).label('similarity')
            )
            .where(KBChunk.kb_version == kb_version)
            .order_by(KBChunk.embedding.cosine_distance(query_embedding))
            .limit(top_k)
        )

        result = await session.execute(query)
        rows = result.all()

        if not rows:
            logger.warning("No chunks found in database")
            return {
                'chunks': [],
                'is_confident': False,
                'max_similarity': 0.0
            }

        chunks = []
        max_similarity = 0.0

        for row in rows:
            similarity = float(row.similarity)
            max_similarity = max(max_similarity, similarity)

            chunks.append({
                'chunk_id': row.chunk_id,
                'source_file': row.source_file,
                'section_heading': row.section_heading,
                'content': row.content,
                'chunk_index': row.chunk_index,
                'similarity': similarity
            })

        is_confident = max_similarity >= similarity_threshold

        logger.info(
            f"Retrieved {len(chunks)} chunks, "
            f"max_similarity={max_similarity:.3f}, "
            f"confident={is_confident}"
        )

        return {
            'chunks': chunks,
            'is_confident': is_confident,
            'max_similarity': max_similarity
        }

    except Exception as e:
        logger.error(f"Error during retrieval: {e}")
        raise
