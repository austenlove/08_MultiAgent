"""Researcher 에이전트 — RAG/웹 검색 결과를 모아 컨텍스트로 압축."""
from __future__ import annotations

from typing import Any

from ..retrieval import hybrid_search, web_search
from ..schemas import PlannerDecision, ResearchBundle
from .base import chat_completion, load_prompt


def _format_hit_for_summary(hit: dict[str, Any]) -> str:
    meta = hit.get("meta") or {}
    src = meta.get("source", "unknown")
    page = meta.get("page_number")
    page_str = f" p.{page}" if page else ""
    text = (hit.get("text") or "")[:800]
    return f"[{src}{page_str}]\n{text}"


def _format_web_for_summary(item: dict[str, Any]) -> str:
    title = item.get("title") or "(no title)"
    url = item.get("url") or ""
    content = (item.get("content") or "")[:600]
    return f"[{title} | {url}]\n{content}"


def _collect_sources(rag_hits: list[dict], web_hits: list[dict]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for h in rag_hits:
        meta = h.get("meta") or {}
        src = str(meta.get("source") or "")
        if src and src not in seen:
            seen.add(src)
            ordered.append(src)
    for h in web_hits:
        url = str(h.get("url") or "")
        if url and url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def run_researcher(decision: PlannerDecision) -> ResearchBundle:
    """Planner 결정에 따라 검색을 수행하고 ResearchBundle 을 반환."""
    rag_hits: list[dict] = []
    web_hits: list[dict] = []

    if decision.need_rag and decision.rag_queries:
        for q in decision.rag_queries:
            rag_hits.extend(hybrid_search(q, k=5))

    if decision.need_web and decision.web_queries:
        for q in decision.web_queries:
            res = web_search(q, max_results=4)
            web_hits.extend(res.get("results") or [])

    sources = _collect_sources(rag_hits, web_hits)

    if not rag_hits and not web_hits:
        return ResearchBundle(
            rag_hits=[],
            web_hits=[],
            context_summary="",
            sources=sources,
        )

    # LLM 요약 단계
    rag_block = "\n\n".join(_format_hit_for_summary(h) for h in rag_hits[:8])
    web_block = "\n\n".join(_format_web_for_summary(h) for h in web_hits[:6])
    user_prompt = (
        "[Planner 결정 근거]\n"
        f"{decision.rationale}\n\n"
        "[RAG 결과]\n"
        f"{rag_block or '(없음)'}\n\n"
        "[웹 검색 결과]\n"
        f"{web_block or '(없음)'}\n\n"
        "위 자료를 보강 컨텍스트 요약으로 작성하세요."
    )
    try:
        summary = chat_completion(
            system=load_prompt("researcher"),
            user=user_prompt,
            temperature=0.2,
            max_tokens=900,
        )
    except Exception:
        # 요약이 실패해도 hits 자체는 유지 — Analyst 가 raw 로 보강할 수 있다.
        summary = ""

    return ResearchBundle(
        rag_hits=rag_hits,
        web_hits=web_hits,
        context_summary=summary,
        sources=sources,
    )
