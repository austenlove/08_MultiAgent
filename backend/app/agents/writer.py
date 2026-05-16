"""Writer 에이전트 — 최종 사용자 답변 마크다운을 생성한다."""
from __future__ import annotations

from ..schemas import (
    ChatMessage,
    DocReport,
    PlannerDecision,
    ResearchBundle,
    ValidationResult,
)
from .base import chat_completion, load_prompt


def _build_user_prompt(
    user_message: str,
    history: list[ChatMessage],
    decision: PlannerDecision,
    research: ResearchBundle | None,
    report: DocReport | None,
    validation: ValidationResult | None,
) -> str:
    hist = ""
    if history:
        hist = "[이전 대화 발췌]\n" + "\n".join(
            f"- {m.role}: {m.content[:160]}" for m in history[-4:]
        ) + "\n"

    ctx = (research.context_summary if research else "") or ""
    ctx_block = f"\n[보강 컨텍스트]\n{ctx}\n" if ctx else ""

    report_block = ""
    if report is not None:
        report_block = f"\n[DocReport JSON]\n{report.model_dump_json(indent=2)}\n"

    validation_block = ""
    if validation is not None and not validation.passed:
        issues = "\n".join(f"- {i}" for i in validation.issues[:6])
        validation_block = (
            "\n[검증 실패 — 위 결과가 일부 부족할 수 있음을 사용자에게 한 줄로 안내]\n"
            f"{issues}\n"
        )

    mode_block = f"[Planner 결정 mode = {decision.mode}]\n"
    return (
        f"{mode_block}"
        f"[사용자 메시지]\n{user_message}\n"
        f"{hist}"
        f"{ctx_block}"
        f"{report_block}"
        f"{validation_block}"
        "\n위 자료를 바탕으로 한국어 마크다운 답변을 작성하세요."
    )


def run_writer(
    user_message: str,
    history: list[ChatMessage],
    decision: PlannerDecision,
    research: ResearchBundle | None,
    report: DocReport | None,
    validation: ValidationResult | None,
) -> str:
    return chat_completion(
        system=load_prompt("writer"),
        user=_build_user_prompt(
            user_message, history, decision, research, report, validation
        ),
        temperature=0.3,
        max_tokens=1200,
    )
