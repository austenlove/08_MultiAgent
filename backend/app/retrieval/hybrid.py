"""Hybrid retrieval (Dense + BM25 + RRF + Rerank).

07_SingleAgent 의 retriever.py 를 분해하여 (1) 클라이언트, (2) 검색, (3) 재정렬
세 책임을 명확히 분리했다. 외부에서는 `hybrid_search` 만 사용한다.
"""
from __future__ import annotations

import os
import pickle
import re
from typing import Any

from rank_bm25 import BM25Okapi

from ..config import settings
from .clients import chroma_client, embed, openai_client

UPLOAD_COLLECTION = "current_doc"
STATIC_COLLECTION = "static_docs"
_BM25_CACHE: dict[str, Any] | None = None


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\W+", text.lower()) if t]


def _load_bm25() -> dict[str, list]:
    """디스크 BM25 인덱스를 모듈 캐시에 1회만 로드."""
    global _BM25_CACHE
    if _BM25_CACHE is not None:
        return _BM25_CACHE

    path = settings.bm25_path
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = pickle.load(f)
        if "corpus" in data and "metadatas" in data:
            _BM25_CACHE = data
            return data
    _BM25_CACHE = {"corpus": [], "metadatas": []}
    return _BM25_CACHE


def _dense_hits(question_embed: list[float], k: int) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    client = chroma_client()
    for name in (UPLOAD_COLLECTION, STATIC_COLLECTION):
        try:
            coll = client.get_collection(name=name)
        except Exception:
            continue
        if coll.count() == 0:
            continue
        n = min(k, coll.count())
        res = coll.query(query_embeddings=[question_embed], n_results=n)
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        ids = (res.get("ids") or [[]])[0]
        for cid, doc, meta in zip(ids, docs, metas):
            meta = meta or {}
            text = meta.get("original_text") or doc
            hits.append({"id": cid, "text": text, "meta": meta})
    return hits


def _sparse_hits(question: str, k: int) -> list[dict[str, Any]]:
    data = _load_bm25()
    if not data["corpus"]:
        return []
    bm25 = BM25Okapi(data["corpus"])
    scores = bm25.get_scores(_tokenize(question))
    if len(scores) == 0:
        return []
    top_n = min(k, len(scores))
    indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_n]
    out = []
    for idx in indices:
        meta = data["metadatas"][idx] or {}
        text = meta.get("original_text") or ""
        out.append(
            {"id": f"bm25::{idx}", "text": text, "meta": meta, "score": float(scores[idx])}
        )
    return out


def _rrf_fuse(*hit_lists: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    fused: dict[str, dict[str, Any]] = {}
    for hits in hit_lists:
        for rank, hit in enumerate(hits):
            meta = hit.get("meta") or {}
            key = (
                f"{meta.get('document_hash') or meta.get('source', '')}"
                f"_{meta.get('page_number', 0)}_{hash(hit['text'])}"
            )
            entry = fused.setdefault(key, {"score": 0.0, "hit": hit})
            entry["score"] += 1.0 / (60 + rank + 1)
    ordered = sorted(fused.values(), key=lambda x: x["score"], reverse=True)
    return [entry["hit"] for entry in ordered[:top_k]]


def _rerank(question: str, candidates: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    if not candidates:
        return []
    passages = []
    for i, c in enumerate(candidates):
        meta = c.get("meta") or {}
        src = meta.get("source", "unknown")
        page = meta.get("page_number")
        page_str = f" (p.{page})" if page else ""
        passages.append(f"[{i+1}] {src}{page_str}\n{c['text'][:600]}")
    prompt = (
        "당신은 검색된 문서 청크의 관련성을 평가하는 전문가입니다.\n"
        "아래 [질문]에 대해 각 [청크]가 얼마나 관련 있는지 0~10 사이의 정수 점수를 매겨 주세요.\n\n"
        f"[질문]\n{question}\n\n"
        f"[청크 목록]\n" + "\n\n".join(passages) +
        "\n\n출력 형식 (다른 내용 없이 숫자만, 예: 1:8,2:3,3:9):"
    )
    try:
        resp = openai_client().chat.completions.create(
            model=settings.chat_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=128,
        )
        raw = (resp.choices[0].message.content or "").strip()
        scores: dict[int, float] = {}
        for item in raw.split(","):
            if ":" not in item:
                continue
            idx_str, score_str = item.split(":", 1)
            try:
                idx = int(idx_str.strip()) - 1
                score = float(score_str.strip())
            except ValueError:
                continue
            if 0 <= idx < len(candidates):
                scores[idx] = score
        if not scores:
            return candidates[:top_n]
        ordered_indices = sorted(scores.keys(), key=lambda i: scores[i], reverse=True)[:top_n]
        return [candidates[i] for i in ordered_indices]
    except Exception:
        return candidates[:top_n]


def hybrid_search(question: str, k: int = 5) -> list[dict[str, Any]]:
    """Return a ranked list of context chunks with metadata.

    빈 질의가 들어와도 안전하게 빈 리스트를 반환한다.
    """
    question = (question or "").strip()
    if not question:
        return []
    embedded = embed([question])
    if not embedded:
        return []
    q_embed = embedded[0]
    dense = _dense_hits(q_embed, k=k * 2)
    sparse = _sparse_hits(question, k=k * 2)
    fused = _rrf_fuse(dense, sparse, top_k=k * 2)
    return _rerank(question, fused, top_n=k)
