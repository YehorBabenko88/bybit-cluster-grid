import json
import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path


MAX_LOG_MESSAGE=16000
MAX_LOG_EXCEPTION=32000
_EXTRA_FIELDS=("node_id","symbol","event","attempt","delay","component","queue_depth",
               "queue_ratio","spool_ratio","disk_pressure_state","process_rss",
               "process_cpu_pct","lease_generation","job_id","version")

def _bounded(value,limit):
    text=str(value)
    return text if len(text)<=limit else text[:limit]+"...[truncated]"

class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": time.time(),
            "level": record.levelname,
            "logger": record.name,
            "msg": _bounded(record.getMessage(),MAX_LOG_MESSAGE),
        }

        for k in _EXTRA_FIELDS:
            if hasattr(record, k):
                payload[k] = getattr(record, k)

        if record.exc_info:
            payload["exc"] = _bounded(self.formatException(record.exc_info),MAX_LOG_EXCEPTION)

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
