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


def setup_logging():
    level = getattr(
        logging,
        os.getenv("LOG_LEVEL", "INFO").upper(),
        logging.INFO,
    )

    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        return

    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = JsonFormatter()

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)

    fh = logging.handlers.RotatingFileHandler(
        log_dir / "grid.jsonl",
        maxBytes=50_000_000,
        backupCount=10,
        encoding="utf-8",
    )
    fh.setFormatter(formatter)

    root.addHandler(sh)
    root.addHandler(fh)
