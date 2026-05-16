"""평가 러너.

요구사항 2: 코드 검증과 LLM 판단을 별도로 집계해 리포트한다.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.app.orchestrator import run_pipeline
from backend.app.schemas import AgentStep

from evaluation.evaluators import (
    faithfulness,
    requirement_coverage,
    retrieval_precision,
    structural_code_checks,
)
from evaluation.schemas import (
    AggregateReport,
    CodeCheckScore,
    EvaluationResult,
    LLMJudgmentScore,
    TestCase,
)


def _avg(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _extract_retrieved_sources(trace: list[AgentStep]) -> list[str]:
    """trace 의 researcher 단계 preview 에서 출처 키워드를 추출 (가벼운 휴리스틱).

    상세 출처는 DocReport.references 에서도 보강한다.
    """
    sources: list[str] = []
    for step in trace:
        if step.agent == "researcher" and step.payload_preview:
            sources.append(step.payload_preview)
    return sources


class EvaluationRunner:
    def run(self, test_cases_path: str | Path) -> None:
        with open(test_cases_path, "r", encoding="utf-8") as f:
            cases = [TestCase(**c) for c in json.load(f)]

        results: list[EvaluationResult] = []
        for case in cases:
            print(f"[{case.id}] running pipeline → {case.query[:60]}")
            response = run_pipeline(
                user_message=case.query,
                history=[],
                uploaded_document=case.uploaded_document,
            )
            retrieved_sources = _extract_retrieved_sources(response.agent_trace)
            # references 도 정답 매칭의 근거가 되도록 합쳐 평가.
            if response.doc_report:
                retrieved_sources.extend(response.doc_report.references)

            # ─ 코드 검증 그룹 ─
            code_scores: list[CodeCheckScore] = []
            code_scores.append(
                retrieval_precision(retrieved_sources, case.expected_doc_ids)
            )
            code_scores.extend(structural_code_checks(response.doc_report))

            # ─ LLM 판단 그룹 ─
            context_text = ""
            for step in response.agent_trace:
                if step.agent == "researcher" and step.payload_preview:
                    context_text += step.payload_preview + "\n"
            llm_scores: list[LLMJudgmentScore] = [
                faithfulness(case.query, context_text, response.reply),
                requirement_coverage(case.requirements, response.reply),
            ]

            avg_code = _avg(s.score for s in code_scores if s.status != "skip")
            avg_llm = _avg(s.score for s in llm_scores if s.status != "skip")
            overall = _avg([avg_code, avg_llm])

            results.append(
                EvaluationResult(
                    test_case_id=case.id,
                    query=case.query,
                    generated_reply=response.reply,
                    has_doc_report=response.doc_report is not None,
                    retrieved_sources=retrieved_sources[:10],
                    code_checks=code_scores,
                    llm_judgments=llm_scores,
                    avg_code_score=avg_code,
                    avg_llm_score=avg_llm,
                    overall_score=overall,
                )
            )
            print(
                f"  → code={avg_code:.2f} llm={avg_llm:.2f} overall={overall:.2f}"
            )

        report = self._aggregate(results)
        self._save(report)

    def _aggregate(self, results: list[EvaluationResult]) -> AggregateReport:
        n = len(results)
        code_pass: dict[str, list[int]] = {}
        llm_avg: dict[str, list[float]] = {}
        for r in results:
            for c in r.code_checks:
                code_pass.setdefault(c.name, []).append(
                    1 if c.status == "pass" else 0 if c.status == "fail" else -1
                )
            for j in r.llm_judgments:
                if j.status != "skip":
                    llm_avg.setdefault(j.name, []).append(j.score)

        code_pass_rate = {
            name: (
                sum(1 for v in values if v == 1)
                / max(1, sum(1 for v in values if v != -1))
            )
            for name, values in code_pass.items()
        }
        llm_avg_score = {name: _avg(values) for name, values in llm_avg.items()}

        return AggregateReport(
            total_cases=n,
            avg_code_score=_avg(r.avg_code_score for r in results),
            avg_llm_score=_avg(r.avg_llm_score for r in results),
            avg_overall_score=_avg(r.overall_score for r in results),
            code_check_pass_rate=code_pass_rate,
            llm_judgment_avg=llm_avg_score,
            results=results,
        )

    def _save(self, report: AggregateReport) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path("evaluation") / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)

        json_path = out_dir / f"report_{ts}.json"
        md_path = out_dir / f"report_{ts}.md"

        json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        md_lines: list[str] = []
        md_lines.append(f"# MultiAgent RAG Evaluation Report ({ts})\n")
        md_lines.append("## 1. Summary\n")
        md_lines.append(f"- Total Cases: {report.total_cases}")
        md_lines.append(f"- Overall: **{report.avg_overall_score:.2f}**")
        md_lines.append(f"  - Code Checks Avg: {report.avg_code_score:.2f}")
        md_lines.append(f"  - LLM Judgments Avg: {report.avg_llm_score:.2f}\n")

        md_lines.append("## 2. Code Checks (rule-based, no LLM)\n")
        for name, rate in report.code_check_pass_rate.items():
            md_lines.append(f"- `{name}` pass rate: {rate * 100:.0f}%")
        md_lines.append("")

        md_lines.append("## 3. LLM Judgments\n")
        for name, score in report.llm_judgment_avg.items():
            md_lines.append(f"- `{name}` avg score: {score:.2f}")
        md_lines.append("")

        md_lines.append("## 4. Per-case Results\n")
        for r in report.results:
            md_lines.append(f"### [{r.test_case_id}] {r.query}")
            md_lines.append(
                f"- code={r.avg_code_score:.2f} llm={r.avg_llm_score:.2f} overall={r.overall_score:.2f}"
            )
            for c in r.code_checks:
                md_lines.append(f"  - 🧪 `{c.name}` {c.status} ({c.score:.2f}) — {c.detail}")
            for j in r.llm_judgments:
                md_lines.append(f"  - 🧠 `{j.name}` {j.status} ({j.score:.2f}) — {j.reason}")
            md_lines.append("")

        md_path.write_text("\n".join(md_lines), encoding="utf-8")

        print(f"\n[Done] Reports saved:")
        print(f"  - JSON: {json_path}")
        print(f"  - Markdown: {md_path}")


if __name__ == "__main__":
    runner = EvaluationRunner()
    cases_path = Path(__file__).resolve().parent / "test_cases.json"
    if not cases_path.exists():
        print(f"Error: {cases_path} not found.")
        sys.exit(1)
    runner.run(cases_path)
