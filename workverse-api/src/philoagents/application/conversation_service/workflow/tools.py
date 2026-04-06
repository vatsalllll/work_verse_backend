from functools import lru_cache

from langchain.tools.retriever import create_retriever_tool

from philoagents.application.rag.retrievers import get_retriever
from philoagents.config import settings


@lru_cache(maxsize=1)
def _get_retriever():
    """Lazy-load the retriever (and embedding model) on first use."""
    return get_retriever(
        embedding_model_id=settings.RAG_TEXT_EMBEDDING_MODEL_ID,
        k=settings.RAG_TOP_K,
        device=settings.RAG_DEVICE,
    )


@lru_cache(maxsize=1)
def _get_retriever_tool():
    """Lazy-load the retriever tool on first use."""
    return create_retriever_tool(
        _get_retriever(),
        "retrieve_philosopher_context",
        "Search and return information about a specific philosopher. Always use this tool when the user asks you about a philosopher, their works, ideas or historical context.",
    )


class _LazyTools:
    """Lazy proxy for the tools list so the embedding model isn't loaded at import time."""

    def __iter__(self):
        return iter([_get_retriever_tool()])

    def __getitem__(self, idx):
        return [_get_retriever_tool()][idx]

    def __len__(self):
        return 1


tools = _LazyTools()