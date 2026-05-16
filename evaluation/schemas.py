"""평가 스키마.

요구사항 2: 평가 항목을 "코드 검증" 과 "LLM 판단" 으로 명시적으로 분리한다.
- code_checks: retrieval precision, schema 규칙 등 결정적 점수
- llm_judgments: faithfulness, requirement_coverage 등 LLM 판단 점수
- aggregate: 항목별 평균을 별도로 노출 (혼합 평균은 보조 지표)
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CheckStatus = Literal["pass", "fail", "skip"]


class TestCase(BaseModel):
    id: str
    query: str
    expected_doc_ids: list[str] = Field(
        default_factory=list, description="Retrieval 평가용 기대 출처(파일명 일부 매치)"
    )
    requirements: list[str] = Field(
        default_factory=list, description="Coverage 평가용 요구사항 체크리스트"
    )
    uploaded_document: str | None = Field(
        default=None, description="테스트 시 사전 업로드된 문서 텍스트"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── 코드 검증 항목 (LLM 호출 없음) ────────────────────────────────────────────
class CodeCheckScore(BaseModel):
    name: str
    status: CheckStatus
    score: float = Field(0.0, ge=0.0, le=1.0)
    detail: str = ""


# ── LLM 판단 항목 ─────────────────────────────────────────────────────────────
class LLMJudgmentScore(BaseModel):
    name: str
    status: CheckStatus
    score: float = Field(0.0, ge=0.0, le=1.0)
    reason: str = ""


class EvaluationResult(BaseModel):
    """한 테스트 케이스의 결과 — 두 그룹을 분리해서 노출."""
    test_case_id: str
    query: str
    generated_reply: str = ""
    has_doc_report: bool = False
    retrieved_sources: list[str] = Field(default_factory=list)

    code_checks: list[CodeCheckScore] = Field(default_factory=list)
    llm_judgments: list[LLMJudgmentScore] = Field(default_factory=list)

    avg_code_score: float = 0.0
    avg_llm_score: float = 0.0
    overall_score: float = 0.0


class AggregateReport(BaseModel):
    total_cases: int
    avg_code_score: float
    avg_llm_score: float
    avg_overall_score: float
    code_check_pass_rate: dict[str, float] = Field(
        default_factory=dict,
        description="규칙별 통과율 (0.0~1.0)",
    )
    llm_judgment_avg: dict[str, float] = Field(
        default_factory=dict,
        description="LLM 판단 항목별 평균 점수",
    )
    results: list[EvaluationResult]
