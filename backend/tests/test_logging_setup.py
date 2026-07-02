import logging
from pathlib import Path

import app.logging_setup as logging_setup


def _reset(monkeypatch, tmp_path: Path) -> Path:
    log_file = tmp_path / "logs" / "backend.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.setattr(logging_setup, "_configured", False)
    return log_file


def test_configure_logging_writes_to_file(monkeypatch, tmp_path: Path) -> None:
    log_file = _reset(monkeypatch, tmp_path)

    configured_path = logging_setup.configure_logging()

    assert configured_path == log_file
    logging.getLogger("app.services.planner").info("hello from the planner")
    contents = log_file.read_text(encoding="utf-8")
    assert "Logging configured" in contents
    assert "hello from the planner" in contents
    assert "app.services.planner" in contents


def test_configure_logging_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    log_file = _reset(monkeypatch, tmp_path)

    logging_setup.configure_logging()
    logging_setup.configure_logging()

    app_logger = logging.getLogger("app")
    file_handlers = [
        handler
        for handler in app_logger.handlers
        if isinstance(handler, logging.handlers.RotatingFileHandler)
    ]
    assert len(file_handlers) == 1

    logging.getLogger("app.routes.planner").warning("only once")
    contents = log_file.read_text(encoding="utf-8")
    assert contents.count("only once") == 1


def test_log_level_env_override(monkeypatch, tmp_path: Path) -> None:
    log_file = _reset(monkeypatch, tmp_path)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    logging_setup.configure_logging()

    logging.getLogger("app.services.planner").debug("debug detail")
    assert "debug detail" in log_file.read_text(encoding="utf-8")
