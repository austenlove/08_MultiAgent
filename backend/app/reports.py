"""DocReport JSON 영속화 저장소.

요구사항 5: 백엔드 API 가 커리큘럼(=분석 결과) JSON 저장/목록/다운로드를 제공해야 한다.
파일시스템 기반의 간단한 저장소로 구현하며, 운영 환경에서는 동일 인터페이스로
DB·오브젝트 스토리지로 교체할 수 있다.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .schemas import DocReport, ReportRecord, ReportSummary, ValidationResult


def _reports_dir() -> Path:
    path = settings.reports_path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_id(value: str) -> str:
    """파일 시스템 안전 ID. 외부에서 들어온 ID 의 traversal 차단."""
    out = "".join(ch for ch in value if ch.isalnum() or ch in "-_")
    return out[:64]


def save_report(
    *,
    user: str | None,
    user_message: str,
    doc_report: DocReport,
    validation_result: ValidationResult | None,
) -> ReportRecord:
    rid = uuid.uuid4().hex[:12]
    record = ReportRecord(
        id=rid,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        user=user,
        user_message=user_message[:500],
        doc_report=doc_report,
        validation_result=validation_result,
    )
    path = _reports_dir() / f"{rid}.json"
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return record


def list_reports(limit: int = 50) -> list[ReportSummary]:
    items: list[ReportSummary] = []
    for p in sorted(
        _reports_dir().glob("*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            doc = data.get("doc_report") or {}
            val = data.get("validation_result") or {}
            items.append(
                ReportSummary(
                    id=data.get("id", p.stem),
                    document_title=doc.get("document_title", "(제목 없음)"),
                    created_at=data.get("created_at", ""),
                    validation_passed=bool(val.get("passed", False)) if val else False,
                    attempts=int((val or {}).get("attempts", 1)),
                )
            )
        except (json.JSONDecodeError, OSError):
            continue
    return items


def get_report(report_id: str) -> ReportRecord | None:
    rid = _safe_id(report_id)
    if not rid:
        return None
    path = _reports_dir() / f"{rid}.json"
    if not path.exists():
        return None
    try:
        return ReportRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def report_path(report_id: str) -> Path | None:
    rid = _safe_id(report_id)
    if not rid:
        return None
    path = _reports_dir() / f"{rid}.json"
    return path if path.exists() else None
