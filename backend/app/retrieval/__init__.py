"""Retrieval & helper layer.

Multi-agent 환경에서 공용으로 쓰이는 검색/임베딩/외부검색 도우미를
모아 단일 진입점을 노출한다. 에이전트 코드는 hybrid_search / web_search
함수만 import 하면 되도록 한다.
"""
from .hybrid import hybrid_search
from .web import web_search

__all__ = ["hybrid_search", "web_search"]
