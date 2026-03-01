import logging
from typing import Optional

logger = logging.getLogger(__name__)

_UPSERT_BATCH_SIZE = 100  # Pinecone recommended batch size
_EMBED_MODEL = "llama-text-embed-v2"
_EMBED_DIMENSION = 768  # match the existing Pinecone index
_EMBED_BATCH_SIZE = 96  # Pinecone inference max texts per call


class PineconeClient:
    """
    Wrapper for Pinecone vector database + inference operations.
    Metadata per vector must stay under 40KB — store chunk text only, not full transcripts.
    """

    def __init__(self):
        from pinecone import Pinecone
        from django.conf import settings

        self._pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        self._index = self._pc.Index(settings.PINECONE_INDEX)
        logger.info("PineconeClient connected to index=%s", settings.PINECONE_INDEX)

    def embed_texts(
        self,
        texts: list[str],
        input_type: str = "passage",
    ) -> list[list[float]]:
        """
        Embed texts via Pinecone Inference (llama-text-embed-v2).
        input_type should be "passage" for documents and "query" for search queries.
        Returns list of float vectors (768-dim), same order as input.
        """
        results: list[list[float]] = []
        total = len(texts)
        for i in range(0, total, _EMBED_BATCH_SIZE):
            batch = texts[i: i + _EMBED_BATCH_SIZE]
            response = self._pc.inference.embed(
                model=_EMBED_MODEL,
                inputs=batch,
                parameters={
                    "input_type": input_type,
                    "truncate": "END",
                    "dimension": _EMBED_DIMENSION,
                },
            )
            results.extend(e["values"] for e in response.data)
            logger.debug("Embedded %d/%d texts via Pinecone", min(i + _EMBED_BATCH_SIZE, total), total)
        return results

    def upsert_vectors(
        self,
        vectors: list[dict],  # [{"id": str, "values": list[float], "metadata": dict}]
        namespace: str = "",
    ) -> None:
        """Upsert vectors in batches of 100."""
        total = len(vectors)
        for i in range(0, total, _UPSERT_BATCH_SIZE):
            batch = vectors[i: i + _UPSERT_BATCH_SIZE]
            self._index.upsert(vectors=batch, namespace=namespace)
            logger.debug("Upserted %d/%d vectors", min(i + _UPSERT_BATCH_SIZE, total), total)
        logger.info("Upserted %d vectors to namespace=%s", total, namespace)

    def query(
        self,
        vector: list[float],
        top_k: int = 20,
        namespace: str = "",
        filter: Optional[dict] = None,
    ) -> list[dict]:
        """
        Query for nearest neighbours.
        Returns list of match dicts with keys: id, score, metadata.
        """
        kwargs = {
            "vector": vector,
            "top_k": top_k,
            "namespace": namespace,
            "include_metadata": True,
        }
        if filter:
            kwargs["filter"] = filter

        response = self._index.query(**kwargs)
        return [
            {"id": m.id, "score": m.score, "metadata": m.metadata or {}}
            for m in (response.matches or [])
        ]

    def delete_by_video(self, video_id: str, namespace: str = "") -> None:
        """Delete all vectors for a given video (used when re-indexing)."""
        self._index.delete(
            filter={"video_id": {"$eq": video_id}},
            namespace=namespace,
        )
        logger.info("Deleted vectors for video=%s from namespace=%s", video_id, namespace)
