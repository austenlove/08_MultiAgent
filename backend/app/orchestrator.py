"""멀티에이전트 오케스트레이터.

요구사항 3: 내부 검증 결과를 명시적으로 추적하고, 검증 실패 시 처리 흐름을 안정화한다.

흐름:
  Planner → (Researcher) → Analyst → CodeChecks + LLMJudgments → Writer
                                  │
                                  └─ 실패 시: 피드백을 담아 Analyst 재호출 (최대 N회)

각 단계는 AgentStep 으로 trace 에 기록되어, API 응답으로 그대로 전달된다.
"""
from __future__ import annotations

import logging

from .agents import run_analyst, run_planner, run_researcher, run_writer
from .agents.validator import assemble_validation, run_code_checks, run_llm_judgments
from .config import settings
from . import reports as reports_store
from .schemas import (
    AgentStep,
    ChatMessage,
    ChatResponse,
    DocReport,
    PlannerDecision,
    ResearchBundle,
    ValidationResult,
)

logger = logging.getLogger("multiagent.orchestrator")


def _step(agent: str, status: str, detail: str, payload: str | None = None) -> AgentStep:
    preview = None
    if payload:
        p = payload.replace("\n", " ").strip()
        preview = p if len(p) <= 280 else p[:279] + "…"
    return AgentStep(agent=agent, status=status, detail=detail, payload_preview=preview)


def _run_validation(
    *,
    user_message: str,
    uploaded_document: str | None,
    research: ResearchBundle | None,
    report: DocReport,
    attempts: int,
) -> ValidationResult:
    code = run_code_checks(report)
    # 코드 검증이 통과되어야만 LLM 판단 비용을 지불 (요구사항 4: 불필요 호출 줄이기).
    if any(c.status == "fail" for c in code):
        llm: list = []
        return assemble_validation(code, llm, attempts)
    llm = run_llm_judgments(user_message, uploaded_document, research, report)
    return assemble_validation(code, llm, attempts)


def run_pipeline(
    user_message: str,
    history: list[ChatMessage],
    uploaded_document: str | None,
    user: str | None = None,
) -> ChatResponse:
    trace: list[AgentStep] = []

    # 1) Planner
    decision: PlannerDecision = run_planner(
        user_message=user_message,
        history=history,
        uploaded_document=uploaded_document,
        max_queries=settings.max_research_queries,
    )
    trace.append(
        _step(
            "planner",
            "ok",
            f"mode={decision.mode} need_rag={decision.need_rag} need_web={decision.need_web}",
            decision.rationale,
        )
    )

    # 2) Researcher (조건부)
    research: ResearchBundle | None = None
    if decision.need_rag or decision.need_web:
        try:
            research = run_researcher(decision)
            trace.append(
                _step(
                    "researcher",
                    "ok",
                    f"rag={len(research.rag_hits)} web={len(research.web_hits)}",
                    research.context_summary,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("researcher failed")
            trace.append(_step("researcher", "error", f"{type(exc).__name__}: {exc}"))
            research = None
    else:
        trace.append(_step("researcher", "skipped", "planner 가 검색이 불필요하다고 판단"))

    # 3) Chat 모드: Analyst/Validator 생략하고 Writer 만 호출
    if decision.mode == "chat":
        trace.append(_step("analyst", "skipped", "chat mode"))
        trace.append(_step("validator", "skipped", "chat mode"))
        try:
            reply = run_writer(
                user_message=user_message,
                history=history,
                decision=decision,
                research=research,
                report=None,
                validation=None,
            )
            trace.append(_step("writer", "ok", "chat reply", reply))
            return ChatResponse(
                reply=reply.strip() or "응답을 생성하지 못했습니다.",
                complete=True,
                doc_report=None,
                validation_result=None,
                agent_trace=trace,
                report_id=None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("writer failed (chat mode)")
            trace.append(_step("writer", "error", f"{type(exc).__name__}: {exc}"))
            return ChatResponse(
                reply="답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
                complete=False,
                agent_trace=trace,
            )

    # 4) Analysis 모드: Analyst → Validator (필요 시 재시도)
    max_attempts = max(1, settings.max_validation_retries + 1)
    feedback: list[str] = []
    report: DocReport | None = None
    validation: ValidationResult | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            report = run_analyst(
                user_message=user_message,
                uploaded_document=uploaded_document,
                research=research,
                feedback=feedback or None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("analyst failed on attempt %d", attempt)
            trace.append(
                _step("analyst", "error", f"attempt={attempt}: {type(exc).__name__}: {exc}")
            )
            # Analyst 자체가 망가지면 더 재시도해도 의미 없으므로 즉시 중단.
            break

        trace.append(
            _step(
                "analyst",
                "ok",
                f"attempt={attempt} sections={len(report.sections)} qa={len(report.qa_pairs)}",
                report.overall_summary,
            )
        )

        validation = _run_validation(
            user_message=user_message,
            uploaded_document=uploaded_document,
            research=research,
            report=report,
            attempts=attempt,
        )
        trace.append(
            _step(
                "validator",
                "ok" if validation.passed else "retry" if attempt < max_attempts else "error",
                validation.summary,
                "; ".join(validation.issues) if validation.issues else None,
            )
        )

        if validation.passed:
            break

        # 다음 분석 호출에 넘길 피드백을 명시적으로 누적.
        feedback = validation.issues[:]
        if attempt >= max_attempts:
            break

    # 5) Writer (검증 실패라도 사용자에게 가능한 답을 돌려준다 — 흐름 안정화)
    if report is None:
        reply = (
            "분석에 필요한 정보를 처리하지 못했습니다. "
            "문서를 다시 업로드하거나 질문을 더 구체적으로 작성해 주세요."
        )
        trace.append(_step("writer", "skipped", "analyst 결과 없음"))
        return ChatResponse(
            reply=reply,
            complete=False,
            doc_report=None,
            validation_result=validation,
            agent_trace=trace,
            report_id=None,
        )

    try:
        reply = run_writer(
            user_message=user_message,
            history=history,
            decision=decision,
            research=research,
            report=report,
            validation=validation,
        )
        trace.append(_step("writer", "ok", "analysis reply", reply))
    except Exception as exc:  # noqa: BLE001
        logger.exception("writer failed (analysis mode)")
        trace.append(_step("writer", "error", f"{type(exc).__name__}: {exc}"))
        reply = (
            "분석은 완료되었으나 사용자 응답을 마무리하는 과정에서 오류가 발생했습니다. "
            "DocReport 카드는 그대로 확인하실 수 있습니다."
        )

    # 6) DocReport 영속화 (검증 통과 여부와 무관하게 저장 — 사용자가 다운로드 가능해야 함)
    report_id: str | None = None
    try:
        record = reports_store.save_report(
            user=user,
            user_message=user_message,
            doc_report=report,
            validation_result=validation,
        )
        report_id = record.id
    except Exception:  # noqa: BLE001
        logger.exception("report persistence failed")
        report_id = None

    return ChatResponse(
        reply=reply.strip() or "응답을 생성하지 못했습니다.",
        complete=bool(validation and validation.passed),
        doc_report=report,
        validation_result=validation,
        agent_trace=trace,
        report_id=report_id,
    )
