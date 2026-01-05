"""Qdrant vector database storage.

Handles vector storage and similarity search using Qdrant in embedded mode.
Payload is minimal (photo_id only) - join with SQLite for full data.

Note: Qdrant embedded mode is NOT thread-safe. All operations use a lock
to prevent concurrent access corruption.
"""

import threading
from pathlib import Path
from typing import Sequence

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from fastlrsearch.config import settings


class QdrantStore:
    """Qdrant vector store for image embeddings.

    Uses embedded mode (no Docker required).
    Thread-safe via internal locking.
    """

    def __init__(
        self,
        path: Path | None = None,
        collection_name: str | None = None,
    ):
        """Initialize Qdrant store.

        Args:
            path: Storage directory (defaults to settings)
            collection_name: Collection name (defaults to settings)
        """
        self.path = path or settings.qdrant_path
        self.collection_name = collection_name or settings.qdrant_collection

        # Lazy initialization
        self._client: QdrantClient | None = None

        # Thread safety - Qdrant embedded mode doesn't handle concurrent access well
        self._lock = threading.Lock()

    @property
    def client(self) -> QdrantClient:
        """Get or create Qdrant client."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> QdrantClient:
        """Create Qdrant client and ensure collection exists."""
        # Ensure directory exists
        self.path.mkdir(parents=True, exist_ok=True)

        # Create client in embedded mode
        client = QdrantClient(path=str(self.path))

        # Create collection if it doesn't exist
        collections = client.get_collections().collections
        if not any(c.name == self.collection_name for c in collections):
            self._create_collection(client)

        return client

    def _create_collection(self, client: QdrantClient):
        """Create the photos collection."""
        # Map distance setting to Qdrant Distance enum
        distance_map = {
            "Cosine": Distance.COSINE,
            "Euclid": Distance.EUCLID,
            "Dot": Distance.DOT,
        }
        distance = distance_map.get(settings.vector_distance, Distance.COSINE)

        client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=settings.embedding_dim,
                distance=distance,
            ),
        )
        print(f"Created Qdrant collection '{self.collection_name}'")

    def close(self):
        """Close the client connection."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def upsert(
        self,
        photo_id: str,
        vector: Sequence[float],
    ):
        """Insert or update a single vector.

        Args:
            photo_id: Photo identifier
            vector: Embedding vector
        """
        self.upsert_batch([(photo_id, vector)])

    def upsert_batch(
        self,
        items: Sequence[tuple[str, Sequence[float]]],
    ):
        """Insert or update multiple vectors.

        Args:
            items: List of (photo_id, vector) tuples
        """
        if not items:
            return

        points = [
            PointStruct(
                id=self._hash_id(photo_id),
                vector=list(vector),
                payload={"photo_id": photo_id},
            )
            for photo_id, vector in items
        ]

        with self._lock:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )

    def _hash_id(self, photo_id: str) -> int:
        """Convert string photo_id to integer for Qdrant.

        Qdrant prefers integer IDs for performance.
        """
        # Use first 16 chars of photo_id hex as int
        return int(photo_id[:16], 16)

    def search(
        self,
        vector: Sequence[float],
        limit: int | None = None,
        offset: int = 0,
        threshold: float | None = None,
    ) -> list[tuple[str, float]]:
        """Search for similar vectors.

        Args:
            vector: Query vector
            limit: Max results (defaults to settings.search_k_vec)
            offset: Number of results to skip (for pagination)
            threshold: Minimum similarity score (defaults to settings.default_threshold)

        Returns:
            List of (photo_id, score) tuples, sorted by score descending
        """
        limit = limit or settings.search_k_vec
        threshold = threshold if threshold is not None else settings.default_threshold

        with self._lock:
            # qdrant-client 1.7+ uses query_points() instead of search()
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=list(vector),
                limit=limit,
                offset=offset,
                score_threshold=threshold if threshold > 0 else None,
            )

            return [
                (hit.payload["photo_id"], hit.score)
                for hit in response.points
                if hit.payload is not None
            ]

    def get_vector(self, photo_id: str) -> list[float] | None:
        """Retrieve stored vector for a photo.

        Args:
            photo_id: Photo identifier

        Returns:
            Vector as list of floats, or None if not found
        """
        point_id = self._hash_id(photo_id)
        with self._lock:
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[point_id],
                with_vectors=True,
            )
            if points and len(points) > 0:
                vec = points[0].vector
                if vec is None:
                    return None
                # Handle both dict and list return types from Qdrant
                if isinstance(vec, dict):
                    # Named vectors - get the default one
                    first_vec = list(vec.values())[0] if vec else None
                    return [float(x) for x in first_vec] if first_vec else None  # type: ignore[union-attr]
                return [float(x) for x in vec]  # type: ignore[arg-type]
            return None

    def delete(self, photo_id: str):
        """Delete a vector by photo_id.

        Args:
            photo_id: Photo identifier
        """
        with self._lock:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=[self._hash_id(photo_id)],
            )

    def count(self) -> int:
        """Get total number of vectors in collection."""
        with self._lock:
            info = self.client.get_collection(self.collection_name)
            return info.points_count or 0

    def get_all_ids(self) -> set[str]:
        """Get all photo_ids in the collection.

        Useful for incremental ingestion.
        """
        ids = set()

        with self._lock:
            # Scroll through all points
            offset = None
            while True:
                records, offset = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=1000,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )

                for record in records:
                    if record.payload and "photo_id" in record.payload:
                        ids.add(record.payload["photo_id"])

                if offset is None:
                    break

        return ids


# Global singleton
_store: QdrantStore | None = None


def get_qdrant_store() -> QdrantStore:
    """Get global Qdrant store instance."""
    global _store
    if _store is None:
        _store = QdrantStore()
    return _store


def close_qdrant_store():
    """Close global Qdrant store."""
    global _store
    if _store is not None:
        _store.close()
        _store = None
