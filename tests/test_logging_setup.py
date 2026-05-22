import logging
import sys

import pytest

from ytscribe.logging_setup import setup_logging


def _clear():
    log = logging.getLogger("ytscribe")
    log.handlers.clear()
    log.propagate = True


def test_setup_logging_attaches_one_handler_and_disables_propagate():
    _clear()
    setup_logging()
    log = logging.getLogger("ytscribe")
    assert len(log.handlers) == 1
    assert log.propagate is False
    _clear()


def test_setup_logging_is_idempotent():
    _clear()
    setup_logging()
    setup_logging()
    setup_logging()
    assert len(logging.getLogger("ytscribe").handlers) == 1
    _clear()


def test_setup_logging_raises_clear_error_without_extra(monkeypatch):
    _clear()
    # None in sys.modules makes `import pythonjsonlogger` raise ImportError.
    monkeypatch.setitem(sys.modules, "pythonjsonlogger", None)
    with pytest.raises(ImportError, match="json-logs"):
        setup_logging()
    _clear()
