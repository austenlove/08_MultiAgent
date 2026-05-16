"""Analyst 에이전트 — DocReport JSON 을 생성한다.

OpenAI structured output 으로 스키마 정합성을 보장하고,
재시도 시 [이전 검증 피드백] 을 함께 전달해 결함 항목을 보완한다.
"""
from __future__ import annotations

from pydantic import ValidationError

from ..schemas import DocReport, ResearchBundle
from .base import chat_completion, load_prompt

_DOC_REPORT_SCHEMA = {
    "name": "doc_report",
    "schema": {
        "type": "object",
        "properties": {
            "document_title": {"type": "string"},
            "overall_summary": {"type": "string"},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "key_points": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "summary", "key_points"],
                    "additionalProperties": False,
                },
            },
            "keywords": {"type": "array", "items": {"type": "string"}},
            "qa_pairs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "answer": {"type": "string"},
                    },
                    "required": ["question", "answer"],
                    "additionalProperties": False,
                },
            },
            "references": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "document_title",
            "overall_summary",
            "sections",
            "keywords",
            "qa_pairs",
            "references",
        ],
        "additionalProperties": False,
    },
    "strict": True,
}


def _build_user_prompt(
    user_message: str,
    uploaded_document: str | None,
    research: ResearchBundle | None,
    feedback: list[str] | None,
) -> str:
    document_block = (
        f"\n[분석 대상 문서]\n{uploaded_document.strip()}\n"
        if uploaded_document and uploaded_document.strip()
        else "\n[분석 대상 문서]\n(업로드된 문서 없음 — 검색 결과 및 사용자 질의를 기반으로 분석)\n"
    )
    context_block = ""
    if research and research.context_summary.strip():
        context_block = f"\n[보강 컨텍스트]\n{research.context_summary.strip()}\n"

    feedback_block = ""
    if feedback:
        bullets = "\n".join(f"- {f}" for f in feedback)
        feedback_block = (
            "\n[이전 검증 피드백 — 반드시 이 결함부터 해결할 것]\n"
            f"{bullets}\n"
        )

    return (
        f"[사용자 요청]\n{user_message}\n"
        f"{document_block}"
        f"{context_block}"
        f"{feedback_block}"
    )


def run_analyst(
    user_message: str,
    uploaded_document: str | None,
    research: ResearchBundle | None = None,
    feedback: list[str] | None = None,
) -> DocReport:
    """DocReport 를 생성. 스키마 검증 실패 시 ValueError 를 던진다."""
    raw = chat_completion(
        system=load_prompt("analyst"),
        user=_build_user_prompt(user_message, uploaded_document, research, feedback),
        temperature=0.2,
        response_format={"type": "json_schema", "json_schema": _DOC_REPORT_SCHEMA},
    )
    try:
        return DocReport.model_validate_json(raw)
    except ValidationError as exc:
        raise ValueError(f"analyst schema mismatch: {exc.errors()}") from exc
