"""Structured application logging (O1).

Stdlib-only log configuration suitable for local development and as a
foundation for later production shipping. Every record renders as a single
deterministic JSON line: standard fields (ts, level, logger, msg) merged with
the caller-supplied ``extra={"fields": {...}}`` context (event, project_id,
stage, ...). Never log source contents, uploaded documents, busines secrets,
or credentials; absolute filesystem paths are kept out of every non-error
record.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, TextIO

_RESERVED_FIELD_KEYS = frozenset(logging.makeLogRecord({}).__dict__)


class StructuredFormatter(logging.Formatter):
    """Render one JSON line per record, merging ``extra={"fields": {...}}``."""

    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "fields", None)
        fields = fields if isinstance(fields, dict) else {}
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in fields.items():
            if key not in _RESERVED_FIELD_KEYS:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, sort_keys=True)


def configure_logging(stream: TextIO | None = None, level: int = logging.INFO) -> None:
    """Attach a structured stderr handler to the root logger exactly once.

    Idempotent: repeated calls (e.g. FastAPI reload, test collection importing
    ``app.main`` repeatedly) never add duplicate handlers.
    """
    root = logging.getLogger()
    if any(
        isinstance(h, logging.StreamHandler)
        and getattr(h, "_atp_structured", False)
        for h in root.handlers
    ):
        return
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(StructuredFormatter())
    handler._atp_structured = True
    root.addHandler(handler)
    if root.level > level:
        root.setLevel(level)


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Log one structured event: human-readable message = event name, the
    structured context lives in the ``fields`` dict on the record."""
    logger.log(level, event, extra={"fields": {"event": event, **fields}})