from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .doc_report import DocReport
from .validation import ValidationResult


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    uploaded_document: str | None = Field(
        default=None,
        description="사용자가 업로드한 기술문서의 텍스트 내용 (분석 시 주요 입력으로 활용)",
    )


class PlannerDecision(BaseModel):
    """Planner 에이전트의 의사결정 결과."""
    mode: Literal["chat", "analysis"] = Field(
        ..., description="chat=간단한 질의응답, analysis=DocReport 생성 필요"
    )
    need_rag: bool = Field(False, description="내부 RAG 검색이 필요한가")
    need_web: bool = Field(False, description="외부 웹 검색이 필요한가")
    rag_queries: list[str] = Field(default_factory=list)
    web_queries: list[str] = Field(default_factory=list)
    rationale: str = Field("", description="결정 근거 (디버깅용)")


class ResearchBundle(BaseModel):
    """Researcher 에이전트가 모은 컨텍스트."""
    rag_hits: list[dict[str, Any]] = Field(default_factory=list)
    web_hits: list[dict[str, Any]] = Field(default_factory=list)
    context_summary: str = Field("", description="Analyst 에 넘길 요약 컨텍스트")
    sources: list[str] = Field(default_factory=list, description="중복 제거된 출처 목록")


class AgentStep(BaseModel):
    """오케스트레이터가 추적하는 에이전트 실행 단계."""
    agent: str = Field(..., description="planner / researcher / analyst / validator / writer")
    status: Literal["ok", "error", "skipped", "retry"]
    detail: str = Field("", description="짧은 결과 요약")
    payload_preview: str | None = Field(None, description="결과 미리보기 (디버깅용)")


class ChatResponse(BaseModel):
    reply: str
    complete: bool
    doc_report: DocReport | None = None
    validation_result: ValidationResult | None = None
    agent_trace: list[AgentStep] = Field(default_factory=list)
    report_id: str | None = Field(
        None,
        description="DocReport 가 저장된 경우의 ID (다운로드/조회용)",
    )
