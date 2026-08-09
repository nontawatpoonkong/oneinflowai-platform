"""Qdrant boundary for tenant-safe knowledge point synchronization."""

import uuid
from typing import Any, Protocol

from qdrant_client import AsyncQdrantClient, models

from app.core.exceptions import VectorCollectionConfigurationError


class KnowledgeVectorStore(Protocol):
    async def ensure_collection(self, dimensions: int) -> None: ...
    async def current_point_ids(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> set[uuid.UUID]: ...
    async def upsert(self, points: list[models.PointStruct]) -> None: ...
    async def delete_ids(self, point_ids: set[uuid.UUID]) -> None: ...


class QdrantKnowledgeVectorStore:
    def __init__(self, client: AsyncQdrantClient, *, collection_name: str) -> None:
        self.client = client
        self.collection_name = collection_name

    async def ensure_collection(self, dimensions: int) -> None:
        if not await self.client.collection_exists(self.collection_name):
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=dimensions, distance=models.Distance.COSINE
                ),
            )
        else:
            info = await self.client.get_collection(self.collection_name)
            vectors = info.config.params.vectors
            existing = getattr(vectors, "size", None)
            if existing != dimensions:
                raise VectorCollectionConfigurationError()
        for field in ("workspace_id", "document_id", "chunk_id"):
            await self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )

    def _document_filter(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="workspace_id", match=models.MatchValue(value=str(workspace_id))
                ),
                models.FieldCondition(
                    key="document_id", match=models.MatchValue(value=str(document_id))
                ),
            ]
        )

    async def current_point_ids(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> set[uuid.UUID]:
        point_ids: set[uuid.UUID] = set()
        offset: Any = None
        while True:
            records, offset = await self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=self._document_filter(workspace_id, document_id),
                limit=256,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            point_ids.update(uuid.UUID(str(record.id)) for record in records)
            if offset is None:
                return point_ids

    async def upsert(self, points: list[models.PointStruct]) -> None:
        await self.client.upsert(
            collection_name=self.collection_name, points=points, wait=True
        )

    async def delete_ids(self, point_ids: set[uuid.UUID]) -> None:
        if point_ids:
            await self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=list(point_ids)),
                wait=True,
            )
