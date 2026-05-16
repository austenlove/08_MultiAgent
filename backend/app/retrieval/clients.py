"""싱글톤 클라이언트 헬퍼.

OpenAI / Chroma 클라이언트를 한 곳에서 캐시해, 각 에이전트가
독립적으로 인스턴스를 만들지 않도록 한다 (요구사항 4: 중복 로직 제거).
"""
from __future__ import annotations

import os
from functools import lru_cache

import chromadb
from openai import OpenAI

from ..config import settings


@lru_cache(maxsize=1)
def openai_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


@lru_cache(maxsize=1)
def chroma_client() -> chromadb.api.ClientAPI:
    os.makedirs(settings.chroma_path, exist_ok=True)
    return chromadb.PersistentClient(path=str(settings.chroma_path))


def embed(texts: list[str]) -> list[list[float]]:
    """공용 임베딩 헬퍼 (Researcher / Analyst 양쪽에서 사용)."""
    if not texts:
        return []
    resp = openai_client().embeddings.create(
        model=settings.embedding_model, input=texts
    )
    return [d.embedding for d in resp.data]
