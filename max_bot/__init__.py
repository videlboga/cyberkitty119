"""Max messenger bot integration scaffold.

This package implements provider-aware handlers that enqueue media jobs into the
existing transkribator worker pipeline. It's intentionally small and mirrors the
structure of `bot/` but uses `transkribator_modules` services where possible.
"""
__all__ = ["config", "api_client", "handlers", "jobs", "db"]
