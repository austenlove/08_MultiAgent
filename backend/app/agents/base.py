"""에이전트 공용 헬퍼.

요구사항 1번: 시스템 프롬프트는 코드에서 분리해 외부 파일로 관리한다.
프롬프트 파일은 모듈 로드 시 캐시되며, 운영 중 핫리로드는 지원하지 않는다.
"""
from __future__ import annotations

from functools import lru_cache

from ..config import settings
from ..retrieval.clients import openai_client

__all__ = ["load_prompt", "chat_completion"]


@lru_cache(maxsize=8)
def load_prompt(name: str) -> str:
    """`backend/prompts/<name>.txt` 를 읽어 캐시한다."""
    path = settings.prompts_path / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"prompt file not found: {path}. "
            "Ensure backend/prompts/ contains planner/researcher/analyst/validator/writer.txt"
        )
    return path.read_text(encoding="utf-8").strip()


def chat_completion(
    *,
    system: str,
    user: str,
    temperature: float = 0.2,
    response_format: dict | None = None,
    max_tokens: int | None = None,
) -> str:
    """단발성 LLM 호출 — 모든 에이전트가 공유하는 단일 진입점."""
    kwargs: dict = {
        "model": settings.chat_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    resp = openai_client().chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()
