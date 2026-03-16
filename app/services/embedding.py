import openai
from typing import List
import time
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for creating text embeddings using OpenAI."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.embedding_model
        self.max_retries = 3
        self.base_delay = 1.0

    async def embed_text(self, text: str) -> List[float]:
        """Create an embedding for a single text string."""
        for attempt in range(self.max_retries):
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=text,
                )
                embedding = response.data[0].embedding
                return embedding

            except openai.RateLimitError as e:
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(f"Rate limit hit, retrying in {delay}s: {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"Rate limit exceeded after {self.max_retries} attempts")
                    raise

            except openai.APIError as e:
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(f"API error, retrying in {delay}s: {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"API error after {self.max_retries} attempts: {e}")
                    raise

            except Exception as e:
                logger.error(f"Unexpected error creating embedding: {e}")
                raise


# Global instance
embedding_service = EmbeddingService()
