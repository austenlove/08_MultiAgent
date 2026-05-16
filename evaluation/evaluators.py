"""평가 evaluator 묶음.

요구사항 2: 코드/LLM 두 그룹을 명시적으로 분리.
- CodeChecks: retrieval precision + DocReport 구조 규칙 (백엔드 validator 와 동일 규칙 재사용)
- LLMJudgments: faithfulness + requirement_coverage (LLM 호출)
"""
from __future__ import annotations

import json
import re
from typing import Any

from backend.app.agents.validator import run_code_checks
from backend.app.config import settings
from backend.app.retrieval.clients import openai_client
from backend.app.schemas import DocReport

from .schemas import CodeCheckScore, LLMJudgmentScore


# ── Retrieval precision (코드 검증 그룹) ──────────────────────────────────────
def retrieval_precision(
    retrieved_sources: list[str], expected_doc_ids: list[str]
) -> CodeCheckScore:
    if not expected_doc_ids:
        return CodeCheckScore(
            name="retrieval_precision",
            status="skip",
            score=1.0,
            detail="expected_doc_ids 가 비어 있어 평가 제외",
        )
    matched = sum(
        1 for exp in expected_doc_ids if any(exp in src for src in retrieved_sources)
    )
    score = matched / len(expected_doc_ids)
    return CodeCheckScore(
        name="retrieval_precision",
        status="pass" if score >= 0.5 else "fail",
        score=score,
        detail=f"{matched}/{len(expected_doc_ids)} matched",
    )


# ── DocReport 구조 규칙 (백엔드 validator 의 코드 체크 재사용) ────────────────
def structural_code_checks(report: DocReport | None) -> list[CodeCheckScore]:
    if report is None:
        return [
            CodeCheckScore(
                name="doc_report_present",
                status="fail",
                score=0.0,
                detail="DocReport 없음",
            )
        ]
    results = run_code_checks(report)
    scores: list[CodeCheckScore] = []
    for r in results:
        score = 1.0 if r.status == "pass" else 0.0
        scores.append(
            CodeCheckScore(
                name=r.name,
                status=r.status,
                score=score,
                detail=r.detail or f"{r.actual} (threshold {r.threshold})",
            )
        )
    return scores


# ── LLM 판단 (LLM 호출) ──────────────────────────────────────────────────────
def _ask_llm_json(prompt: str) -> dict[str, Any]:
    try:
        resp = openai_client().chat.completions.create(
            model=settings.chat_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {"error": "no json"}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {"error": "json decode"}


def faithfulness(query: str, context: str, reply: str) -> LLMJudgmentScore:
    prompt = (
        "[Task] 생성된 답변이 제공된 검색 근거(Context) 에 충실한지 평가.\n"
        f"[Query]\n{query}\n\n"
        f"[Context]\n{context or '(없음)'}\n\n"
        f"[Reply]\n{reply}\n\n"
        "결과 형식: {\"score\": 0.0~1.0, \"reason\": \"이유\"}"
    )
    data = _ask_llm_json(prompt)
    if "error" in data:
        return LLMJudgmentScore(
            name="faithfulness", status="skip", score=0.0, reason=data["error"]
        )
    score = max(0.0, min(1.0, float(data.get("score", 0))))
    return LLMJudgmentScore(
        name="faithfulness",
        status="pass" if score >= 0.7 else "fail",
        score=score,
        reason=str(data.get("reason", ""))[:300],
    )


def requirement_coverage(requirements: list[str], reply: str) -> LLMJudgmentScore:
    if not requirements:
        return LLMJudgmentScore(
            name="requirement_coverage",
            status="skip",
            score=1.0,
            reason="requirements 비어 있음",
        )
    req_list = "\n".join(f"- {r}" for r in requirements)
    prompt = (
        "[Task] 요구사항이 답변에 얼마나 반영되었는지 평가.\n"
        f"[Requirements]\n{req_list}\n\n"
        f"[Reply]\n{reply}\n\n"
        "결과 형식: {\"score\": 0.0~1.0, \"reason\": \"이유\"}"
    )
    data = _ask_llm_json(prompt)
    if "error" in data:
        return LLMJudgmentScore(
            name="requirement_coverage", status="skip", score=0.0, reason=data["error"]
        )
    score = max(0.0, min(1.0, float(data.get("score", 0))))
    return LLMJudgmentScore(
        name="requirement_coverage",
        status="pass" if score >= 0.7 else "fail",
        score=score,
        reason=str(data.get("reason", ""))[:300],
    )
