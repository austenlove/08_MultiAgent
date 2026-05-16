"""외부 웹 검색 (Tavily) 호출 헬퍼.

07_SingleAgent 에서는 tool spec 과 결합되어 있었으나, multi-agent 구조에서는
Researcher 가 직접 호출하므로 순수 helper 로 분리했다.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..config import settings

_TAVILY_URL = "https://api.tavily.com/search"


def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Tavily 응답을 표준화된 dict 로 반환.

    네트워크 실패 시 빈 결과 + error 필드를 채워 호출자가 분기 없이 처리할
    수 있도록 한다 (요구사항 4: 불안정한 분기 줄이기).
    """
    query = (query or "").strip()
    if not query:
        return {"query": query, "answer": None, "results": [], "error": "empty query"}

    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": True,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(_TAVILY_URL, json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        return {
            "query": query,
            "answer": None,
            "results": [],
            "error": f"tavily request failed: {exc}",
        }

    results = [
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "content": (item.get("content") or "")[:800],
        }
        for item in (data.get("results") or [])
    ]
    return {
        "query": query,
        "answer": data.get("answer"),
        "results": results,
    }
