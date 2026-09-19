import json, logging, logging.handlers, os, sys, time

class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload={
            "ts": time.time(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k in ("node_id","symbol","event","attempt","delay","component"):
            if hasattr(record,k): payload[k]=getattr(record,k)
        if record.exc_info: payload["exc"]=self.formatException(record.exc_info)
        return json.dumps(payload,ensure_ascii=False)

def setup_logging():
    level=getattr(logging,os.getenv("LOG_LEVEL","INFO").upper(),logging.INFO)
    root=logging.getLogger(); root.setLevel(level)
    if root.handlers: return
    os.makedirs("logs",exist_ok=True)
    sh=logging.StreamHandler(sys.stdout); sh.setFormatter(JsonFormatter())
    fh=logging.handlers.RotatingFileHandler("logs/grid.jsonl",maxBytes=50_000_000,backupCount=10,encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    root.addHandler(sh); root.addHandler(fh)
