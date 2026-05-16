"""Planner 에이전트 — 다음 단계를 결정한다."""
from __future__ import annotations

import json

from pydantic import ValidationError

from ..schemas import ChatMessage, PlannerDecision
from .base import chat_completion, load_prompt

_PLANNER_SCHEMA = {
    "name": "planner_decision",
    "schema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["chat", "analysis"]},
            "need_rag": {"type": "boolean"},
            "need_web": {"type": "boolean"},
            "rag_queries": {"type": "array", "items": {"type": "string"}},
            "web_queries": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string"},
        },
        "required": ["mode", "need_rag", "need_web", "rag_queries", "web_queries", "rationale"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _build_user_prompt(
    user_message: str,
    history: list[ChatMessage],
    uploaded_document: str | None,
) -> str:
    hist_block = ""
    if history:
        last = history[-6:]
        hist_block = "[최근 대화 이력]\n" + "\n".join(
            f"- {m.role}: {m.content[:200]}" for m in last
        )

    doc_block = ""
    if uploaded_document and uploaded_document.strip():
        snippet = uploaded_document.strip()[:1200]
        doc_block = f"\n[업로드 문서 일부]\n{snippet}\n"

    return (
        f"[사용자 메시지]\n{user_message}\n"
        f"{doc_block}"
        f"\n{hist_block}\n"
        "\n위 입력을 보고 JSON 결정만 출력하세요."
    )


def run_planner(
    user_message: str,
    history: list[ChatMessage],
    uploaded_document: str | None,
    max_queries: int,
) -> PlannerDecision:
    """Planner 호출. 파싱 실패 시 보수적인 기본값 (mode=chat) 으로 폴백한다."""
    system = load_prompt("planner")
    user = _build_user_prompt(user_message, history, uploaded_document)
    raw = chat_completion(
        system=system,
        user=user,
        temperature=0.0,
        response_format={"type": "json_schema", "json_schema": _PLANNER_SCHEMA},
    )
    try:
        data = json.loads(raw)
        decision = PlannerDecision(**data)
    except (json.JSONDecodeError, ValidationError, TypeError):
        # Planner 가 망가져도 시스템이 멈추지 않도록 — chat 모드로 폴백.
        return PlannerDecision(
            mode="chat",
            need_rag=False,
            need_web=False,
            rationale="planner output unparsable; falling back to chat mode",
        )

    # 안전: 너무 많은 검색은 잘라낸다.
    decision = decision.model_copy(
        update={
            "rag_queries": [q for q in decision.rag_queries if q.strip()][:max_queries],
            "web_queries": [q for q in decision.web_queries if q.strip()][:max_queries],
        }
    )
    # 업로드 문서 없이 analysis 인 경우 최소 1개의 검색은 강제 (사실 보강).
    if (
        decision.mode == "analysis"
        and not (uploaded_document and uploaded_document.strip())
        and not decision.rag_queries
        and not decision.web_queries
    ):
        decision = decision.model_copy(
            update={"need_rag": True, "rag_queries": [user_message[:120]]}
        )
    return decision
