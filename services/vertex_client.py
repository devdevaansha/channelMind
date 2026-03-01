import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict = {}
_VERTEX_BATCH_SIZE = 5  # Vertex AI text-embedding-004 max texts per call
_VERTEX_MODEL_NAME = "text-embedding-004"


def _get_embedding_model():
    if _VERTEX_MODEL_NAME not in _MODEL_CACHE:
        import vertexai
        from vertexai.language_models import TextEmbeddingModel
        from django.conf import settings

        logger.info("Initializing Vertex AI project=%s region=%s", settings.VERTEX_PROJECT_ID, settings.VERTEX_REGION)
        vertexai.init(
            project=settings.VERTEX_PROJECT_ID,
            location=settings.VERTEX_REGION,
        )
        _MODEL_CACHE[_VERTEX_MODEL_NAME] = TextEmbeddingModel.from_pretrained(_VERTEX_MODEL_NAME)
        logger.info("Vertex AI embedding model loaded.")
    return _MODEL_CACHE[_VERTEX_MODEL_NAME]


class VertexClient:
    """
    Wrapper for Vertex AI text embeddings.
    Batches requests (max 5 texts/call) and returns float vectors.
    """

    def __init__(self):
        self._model = _get_embedding_model()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of texts. Returns a list of float vectors, same order as input.
        Automatically batches into groups of 5.
        """
        results = []
        total = len(texts)
        for i in range(0, total, _VERTEX_BATCH_SIZE):
            batch = texts[i: i + _VERTEX_BATCH_SIZE]
            embeddings = self._embed_batch_with_retry(batch)
            results.extend(embeddings)
            logger.debug("Embedded %d/%d texts", min(i + _VERTEX_BATCH_SIZE, total), total)
        return results

    def _embed_batch_with_retry(self, texts: list[str], max_retries: int = 3) -> list[list[float]]:
        for attempt in range(max_retries):
            try:
                response = self._model.get_embeddings(texts)
                return [e.values for e in response]
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt * 2
                    logger.warning("Vertex embed error (attempt %d): %s; retrying in %ds", attempt + 1, e, wait)
                    time.sleep(wait)
                else:
                    raise
        return []  # unreachable
