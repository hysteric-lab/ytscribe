"""Opt-in JSON logging configuration for the ytscribe namespace.

A library must never configure logging on import. This helper is opt-in: a
consumer (the CLI, the service worker) calls it explicitly. It touches only the
`ytscribe` logger and its children — never the root logger.
"""
from __future__ import annotations

import logging
import sys
from typing import TextIO

_LOGGER_NAME = "ytscribe"


def setup_logging(level: int = logging.INFO, stream: TextIO | None = None) -> None:
    """Attach a JSON-formatted handler to the `ytscribe` logger.

    Idempotent — a repeated call is a no-op. First-call-wins is intentional: to
    change `stream` or `level` mid-process, a caller must clear the `ytscribe`
    logger's handlers first.

    Requires the `json-logs` extra (`pip install ytscribe[json-logs]`).
    """
    try:
        from pythonjsonlogger import jsonlogger
    except ImportError as exc:
        raise ImportError(
            "install ytscribe[json-logs] to enable JSON logging"
        ) from exc

    logger = logging.getLogger(_LOGGER_NAME)
    if any(isinstance(h.formatter, jsonlogger.JsonFormatter)
           for h in logger.handlers):
        return  # idempotent: already configured

    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(
        jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
