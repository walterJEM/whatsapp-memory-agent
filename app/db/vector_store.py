"""
Vector Store — Semantic memory using pgvector + LangChain.
Stores embeddings of notes for natural language search.
"""

from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document
from typing import Optional
import os

from app.utils.logger import get_logger

logger = get_logger(__name__)

CONNECTION_STRING = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:password@localhost:5432/memory_agent"
)


class VectorStore:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.store = PGVector(
            embeddings=self.embeddings,
            collection_name="memory_notes",
            connection=CONNECTION_STRING,
            use_jsonb=True,
        )

    async def add_document(
        self,
        doc_id: str,
        content: str,
        metadata: dict,
    ) -> None:
        """Add a document to the vector store."""
        doc = Document(page_content=content, metadata=metadata, id=doc_id)
        await self.store.aadd_documents([doc], ids=[doc_id])
        logger.debug(f"Added document {doc_id} to vector store")

    async def similarity_search(
        self,
        query: str,
        filters: dict,
        k: int = 5,
        date_filter: Optional[str] = None,
    ) -> list[Document]:
        """
        Search for similar documents using cosine similarity.

        Args:
            query: Natural language search query
            filters: Metadata filters (user_phone, category, etc.)
            k: Number of results to return
            date_filter: 'today', 'this_week', 'this_month'
        """
        if date_filter:
            filters = {**filters, **self._build_date_filter(date_filter)}

        results = await self.store.asimilarity_search_with_score(
            query=query,
            k=k,
            filter=filters,
        )

        # Filter by relevance score (cosine similarity > 0.3)
        return [doc for doc, score in results if score > 0.3]

    def _build_date_filter(self, period: str) -> dict:
        """Build a date range filter for pgvector metadata queries."""
        from datetime import datetime, timedelta

        now = datetime.now()
        if period == "today":
            start = now.replace(hour=0, minute=0, second=0)
        elif period == "this_week":
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0)
        elif period == "this_month":
            start = now.replace(day=1, hour=0, minute=0, second=0)
        else:
            return {}

        return {"created_at": {"$gte": start.isoformat()}}

    async def delete_document(self, doc_id: str) -> None:
        """Delete a document from the vector store."""
        await self.store.adelete(ids=[doc_id])
