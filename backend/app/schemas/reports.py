"""분석 결과(DocReport) JSON 영속화 스키마."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .doc_report import DocReport
from .validation import ValidationResult


class ReportSummary(BaseModel):
    """리스트 화면에서 사용할 메타데이터."""
    id: str
    document_title: str
    created_at: str = Field(..., description="ISO 8601 UTC")
    validation_passed: bool
    attempts: int = 1


class ReportRecord(BaseModel):
    """저장 파일의 전체 내용."""
    id: str
    created_at: str
    user: str | None = None
    user_message: str
    doc_report: DocReport
    validation_result: ValidationResult | None = None
