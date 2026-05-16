"""검증 결과 스키마.

요구사항 2번: 코드로 결정적으로 검증할 수 있는 항목(CodeCheck)과
LLM 판단이 필요한 항목(LLMJudgment)을 명시적으로 분리한다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CheckStatus = Literal["pass", "fail", "skip"]


class CodeCheckResult(BaseModel):
    """결정적 규칙 기반 체크 (LLM 호출 없음)."""
    name: str = Field(..., description="규칙 식별자 (예: 'summary_min_length')")
    status: CheckStatus
    detail: str = Field("", description="실패 사유 또는 통과 근거")
    threshold: str | None = Field(None, description="규칙 임계값 표현 (예: '>= 50자')")
    actual: str | None = Field(None, description="실측 값 표현 (예: '32자')")


class LLMJudgmentResult(BaseModel):
    """LLM 판단 기반 체크 (faithfulness, coverage 등)."""
    name: str = Field(..., description="판단 항목 식별자 (예: 'faithfulness')")
    status: CheckStatus
    score: float = Field(0.0, ge=0.0, le=1.0)
    reason: str = Field("", description="LLM이 제시한 이유")
    passed_threshold: float = Field(0.7, description="status=pass 가 되는 점수 하한")


class ValidationResult(BaseModel):
    """오케스트레이터가 추적하는 종합 검증 결과."""
    passed: bool = Field(..., description="모든 필수 체크가 통과했는지")
    code_checks: list[CodeCheckResult] = Field(default_factory=list)
    llm_judgments: list[LLMJudgmentResult] = Field(default_factory=list)
    summary: str = Field("", description="사용자에게 보여줄 한 줄 요약")
    issues: list[str] = Field(default_factory=list, description="실패 항목의 detail 모음")
    attempts: int = Field(1, ge=1, description="현재까지 시도된 분석 횟수")
