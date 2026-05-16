"""Runtime configuration loaded from environment variables.

Fails fast on missing secrets so deployment regressions surface at boot
instead of during a user request.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable '{name}' is not set. "
            "Configure it in your .env or deployment secrets."
        )
    return value


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    tavily_api_key: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_expire_minutes: int
    admin_username: str
    admin_password: str
    chat_model: str
    embedding_model: str
    chroma_path: Path
    bm25_path: Path
    prompts_path: Path
    reports_path: Path
    max_validation_retries: int
    max_research_queries: int
    cors_origins: list[str]


def load_settings() -> Settings:
    return Settings(
        openai_api_key=_required("OPENAI_API_KEY"),
        tavily_api_key=_required("TAVILY_API_KEY"),
        jwt_secret=os.getenv("JWT_SECRET", "change-me-in-prod"),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        jwt_expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "120")),
        admin_username=_required("ADMIN_USERNAME"),
        admin_password=_required("ADMIN_PASSWORD"),
        chat_model=os.getenv("CHAT_MODEL", "gpt-4o-mini"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        chroma_path=Path(os.getenv("CHROMA_PATH", str(BASE_DIR / "data" / "chroma_db"))),
        bm25_path=Path(os.getenv("BM25_PATH", str(BASE_DIR / "data" / "bm25_index.pkl"))),
        prompts_path=Path(os.getenv("PROMPTS_PATH", str(BASE_DIR / "prompts"))),
        reports_path=Path(os.getenv("REPORTS_PATH", str(BASE_DIR / "data" / "reports"))),
        max_validation_retries=int(os.getenv("MAX_VALIDATION_RETRIES", "2")),
        max_research_queries=int(os.getenv("MAX_RESEARCH_QUERIES", "3")),
        cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()],
    )


settings = load_settings()
