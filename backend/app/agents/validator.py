"""Validator — 코드 검증과 LLM 판단을 명시적으로 분리한다 (요구사항 2).

- run_code_checks: 결정적 규칙. LLM 호출 없음.
- run_llm_judgments: faithfulness / requirement_coverage. LLM 1회 호출.
"""
from __future__ import annotations

import json
import re

from ..schemas import (
    CodeCheckResult,
    DocReport,
    LLMJudgmentResult,
    ResearchBundle,
    ValidationResult,
)
from .base import chat_completion, load_prompt

# 코드 검증 규칙: (name, threshold_text, predicate, actual_fn, fail_detail_fn)
_MIN_SUMMARY_CHARS = 50
_MIN_SECTIONS = 2
_MIN_KEY_POINTS = 2
_MIN_KEYWORDS = 5
_MIN_QA_PAIRS = 2


def _check_summary_length(report: DocReport) -> CodeCheckResult:
    n = len(report.overall_summary.strip())
    passed = n >= _MIN_SUMMARY_CHARS
    return CodeCheckResult(
        name="overall_summary_min_length",
        status="pass" if passed else "fail",
        threshold=f">= {_MIN_SUMMARY_CHARS}자",
        actual=f"{n}자",
        detail="" if passed else f"전체 요약이 {_MIN_SUMMARY_CHARS}자 미만입니다.",
    )


def _check_section_count(report: DocReport) -> CodeCheckResult:
    n = len(report.sections)
    passed = n >= _MIN_SECTIONS
    return CodeCheckResult(
        name="section_min_count",
        status="pass" if passed else "fail",
        threshold=f">= {_MIN_SECTIONS}",
        actual=str(n),
        detail="" if passed else f"섹션이 {_MIN_SECTIONS}개 미만입니다.",
    )


def _check_section_key_points(report: DocReport) -> CodeCheckResult:
    short = [s.title for s in report.sections if len(s.key_points) < _MIN_KEY_POINTS]
    passed = len(short) == 0
    return CodeCheckResult(
        name="section_key_points_min",
        status="pass" if passed else "fail",
        threshold=f"섹션마다 key_points >= {_MIN_KEY_POINTS}",
        actual=f"{len(short)}개 섹션 미달" if short else "전 섹션 통과",
        detail="" if passed else f"key_points 부족 섹션: {', '.join(short)}",
    )


def _check_keyword_count(report: DocReport) -> CodeCheckResult:
    n = len(report.keywords)
    passed = n >= _MIN_KEYWORDS
    return CodeCheckResult(
        name="keyword_min_count",
        status="pass" if passed else "fail",
        threshold=f">= {_MIN_KEYWORDS}",
        actual=str(n),
        detail="" if passed else f"키워드가 {_MIN_KEYWORDS}개 미만입니다.",
    )


def _check_qa_count(report: DocReport) -> CodeCheckResult:
    n = len(report.qa_pairs)
    passed = n >= _MIN_QA_PAIRS
    return CodeCheckResult(
        name="qa_pairs_min_count",
        status="pass" if passed else "fail",
        threshold=f">= {_MIN_QA_PAIRS}",
        actual=str(n),
        detail="" if passed else f"Q&A 가 {_MIN_QA_PAIRS}개 미만입니다.",
    )


def _check_references(report: DocReport) -> CodeCheckResult:
    n = len(report.references)
    passed = n >= 1
    return CodeCheckResult(
        name="references_present",
        status="pass" if passed else "fail",
        threshold=">= 1",
        actual=str(n),
        detail="" if passed else "references 가 비어 있습니다.",
    )


def _check_no_html(report: DocReport) -> CodeCheckResult:
    """모든 텍스트에 HTML 태그가 섞이지 않았는지 (작성 규칙)."""
    pattern = re.compile(r"<[a-zA-Z/][^>]*>")
    leaks: list[str] = []
    for s in report.sections:
        if pattern.search(s.summary) or any(pattern.search(p) for p in s.key_points):
            leaks.append(s.title)
    if pattern.search(report.overall_summary):
        leaks.append("overall_summary")
    passed = len(leaks) == 0
    return CodeCheckResult(
        name="no_html_tags",
        status="pass" if passed else "fail",
        threshold="HTML 태그 0개",
        actual="없음" if passed else f"{len(leaks)}곳",
        detail="" if passed else f"HTML 태그 검출 위치: {', '.join(leaks)}",
    )


_CODE_CHECKS = (
    _check_summary_length,
    _check_section_count,
    _check_section_key_points,
    _check_keyword_count,
    _check_qa_count,
    _check_references,
    _check_no_html,
)


def run_code_checks(report: DocReport) -> list[CodeCheckResult]:
    """LLM 없이 결정적으로 통과/실패가 결정되는 규칙 묶음."""
    return [check(report) for check in _CODE_CHECKS]


_LLM_JUDGMENT_SCHEMA = {
    "name": "llm_judgments",
    "schema": {
        "type": "object",
        "properties": {
            "faithfulness": {
                "type": "object",
                "properties": {
                    "score": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["score", "reason"],
                "additionalProperties": False,
            },
            "requirement_coverage": {
                "type": "object",
                "properties": {
                    "score": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["score", "reason"],
                "additionalProperties": False,
            },
        },
        "required": ["faithfulness", "requirement_coverage"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _build_judge_user_prompt(
    user_message: str,
    uploaded_document: str | None,
    research: ResearchBundle | None,
    report: DocReport,
) -> str:
    doc_snippet = (uploaded_document or "").strip()[:3000]
    ctx = (research.context_summary if research else "") or ""
    return (
        f"[사용자 요청]\n{user_message}\n\n"
        f"[원문 문서]\n{doc_snippet or '(없음)'}\n\n"
        f"[보강 컨텍스트]\n{ctx or '(없음)'}\n\n"
        f"[DocReport JSON]\n{report.model_dump_json(indent=2)}\n\n"
        "위 자료를 기반으로 faithfulness 와 requirement_coverage 를 평가하세요."
    )


def run_llm_judgments(
    user_message: str,
    uploaded_document: str | None,
    research: ResearchBundle | None,
    report: DocReport,
    threshold: float = 0.7,
) -> list[LLMJudgmentResult]:
    """LLM 판단 항목만 단발성 호출로 평가."""
    try:
        raw = chat_completion(
            system=load_prompt("validator"),
            user=_build_judge_user_prompt(user_message, uploaded_document, research, report),
            temperature=0.0,
            response_format={"type": "json_schema", "json_schema": _LLM_JUDGMENT_SCHEMA},
        )
        data = json.loads(raw)
    except Exception:  # noqa: BLE001 — judge 실패 시 다음 단계가 결정적 규칙으로 진행
        # 판단 실패 시 skip 으로 처리 — 오케스트레이터가 결정적 규칙으로 진행.
        return [
            LLMJudgmentResult(
                name="faithfulness",
                status="skip",
                score=0.0,
                reason="judge call failed",
                passed_threshold=threshold,
            ),
            LLMJudgmentResult(
                name="requirement_coverage",
                status="skip",
                score=0.0,
                reason="judge call failed",
                passed_threshold=threshold,
            ),
        ]

    def _one(name: str) -> LLMJudgmentResult:
        item = data.get(name) or {}
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))
        return LLMJudgmentResult(
            name=name,
            status="pass" if score >= threshold else "fail",
            score=score,
            reason=str(item.get("reason", ""))[:400],
            passed_threshold=threshold,
        )

    return [_one("faithfulness"), _one("requirement_coverage")]


def assemble_validation(
    code_checks: list[CodeCheckResult],
    llm_judgments: list[LLMJudgmentResult],
    attempts: int,
) -> ValidationResult:
    """코드 + LLM 결과를 종합해 ValidationResult 로 묶는다."""
    code_failed = [c for c in code_checks if c.status == "fail"]
    llm_failed = [j for j in llm_judgments if j.status == "fail"]
    passed = not code_failed and not llm_failed

    issues = [c.detail for c in code_failed if c.detail]
    issues.extend(f"{j.name}: {j.reason}" for j in llm_failed)

    if passed:
        summary = "모든 코드 규칙과 LLM 판단을 통과했습니다."
    else:
        summary = (
            f"검증 실패: 코드 규칙 {len(code_failed)}건, LLM 판단 {len(llm_failed)}건."
        )

    return ValidationResult(
        passed=passed,
        code_checks=code_checks,
        llm_judgments=llm_judgments,
        summary=summary,
        issues=issues,
        attempts=attempts,
    )


__all__ = [
    "run_code_checks",
    "run_llm_judgments",
    "assemble_validation",
]
