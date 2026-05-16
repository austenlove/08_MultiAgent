"""FastAPI entrypoint for the 08_MultiAgent backend.

Endpoints
---------
- POST /auth/login                  issue JWT
- GET  /auth/verify                 validate JWT
- GET  /health                      liveness + dependency probe
- POST /chat                        run the multi-agent pipeline
- GET  /reports                     list saved DocReport records
- GET  /reports/{id}                fetch a single record
- GET  /reports/{id}/download       download record as .json file
"""
from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import reports as reports_store
from .auth import create_access_token, require_user, verify_credentials
from .config import settings
from .orchestrator import run_pipeline
from .schemas import (
    ChatRequest,
    ChatResponse,
    LoginRequest,
    ReportRecord,
    ReportSummary,
    TokenResponse,
    VerifyResponse,
)

logger = logging.getLogger("multiagent")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="MultiAgent Document Analysis Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "max_validation_retries": settings.max_validation_retries,
        "max_research_queries": settings.max_research_queries,
        "agent_type": "multi_agent_doc_analyzer",
        "agents": ["planner", "researcher", "analyst", "validator", "writer"],
    }


@app.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    if not verify_credentials(body.username, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token, _exp = create_access_token(body.username)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
    )


@app.get("/auth/verify", response_model=VerifyResponse)
def verify(user: str = Depends(require_user)) -> VerifyResponse:
    return VerifyResponse(valid=True, username=user)


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: str = Depends(require_user)) -> ChatResponse:
    logger.info("chat request user=%s len=%d", user, len(body.message))
    try:
        return run_pipeline(
            user_message=body.message,
            history=body.history,
            uploaded_document=body.uploaded_document,
            user=user,
        )
    except Exception as exc:  # noqa: BLE001 — surface to client for ops debugging
        logger.exception("pipeline failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"pipeline error: {exc}",
        ) from exc


@app.get("/reports", response_model=list[ReportSummary])
def reports_list(
    limit: int = 50, _user: str = Depends(require_user)
) -> list[ReportSummary]:
    limit = max(1, min(200, int(limit)))
    return reports_store.list_reports(limit=limit)


@app.get("/reports/{report_id}", response_model=ReportRecord)
def reports_get(report_id: str, _user: str = Depends(require_user)) -> ReportRecord:
    record = reports_store.get_report(report_id)
    if record is None:
        raise HTTPException(status_code=404, detail="report not found")
    return record


@app.get("/reports/{report_id}/download")
def reports_download(report_id: str, _user: str = Depends(require_user)) -> FileResponse:
    path = reports_store.report_path(report_id)
    if path is None:
        raise HTTPException(status_code=404, detail="report not found")
    return FileResponse(
        path=str(path),
        media_type="application/json",
        filename=f"doc_report_{report_id}.json",
    )
