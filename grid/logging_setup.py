import json
import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": time.time(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        for k in ("node_id", "symbol", "event", "attempt", "delay", "component"):
            if hasattr(record, k):
                payload[k] = getattr(record, k)

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def _log_dir():
    program_data = os.environ.get("ProgramData", r"C:\ProgramData")
    return Path(program_data) / "BybitClusterGrid" / "logs"


def _same_log_file(handler, target_path):
    if not isinstance(handler, logging.FileHandler):
        return False

    try:
        current = Path(handler.baseFilename).resolve()
        target = Path(target_path).resolve()
        return current == target
    except Exception:
        return False


def setup_logging():
    level = getattr(
        logging,
        os.getenv("LOG_LEVEL", "INFO").upper(),
        logging.INFO,
    )

    root = logging.getLogger()
    root.setLevel(level)

    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / "grid.jsonl"
    formatter = JsonFormatter()

    # Uvicorn may already have installed console/root handlers.
    # Do not return early: ensure our JSON file handler exists.
    has_grid_file_handler = any(
        _same_log_file(handler, log_path)
        for handler in root.handlers
    )

    if not has_grid_file_handler:
        fh = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=50_000_000,
            backupCount=10,
            encoding="utf-8",
        )
        fh.setLevel(level)
        fh.setFormatter(formatter)
        root.addHandler(fh)

    # Keep an application stdout handler only when root has none
    # other than our own file handler.
    has_stream_handler = any(
        isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
        for handler in root.handlers
    )

    if not has_stream_handler:
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(level)
        sh.setFormatter(formatter)
        root.addHandler(sh)
