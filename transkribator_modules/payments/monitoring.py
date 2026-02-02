"""Simple helpers for payment monitoring/health checks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from transkribator_modules.config import DATA_DIR, logger

_STATUS_FILE = Path(DATA_DIR) / "yukassa_webhook_status.json"


def record_yukassa_webhook_status(status: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Persist last Yukassa webhook ping for external monitoring."""
    payload = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": details or {},
    }
    try:
        tmp_path = _STATUS_FILE.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(_STATUS_FILE)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to record Yukassa webhook status",
            extra={"file": str(_STATUS_FILE), "error": str(exc), "status": status},
        )
