import os, pathlib

def node_credential():
    direct=os.getenv("NODE_CREDENTIAL","").strip()
    if direct:
        return direct
    base=os.getenv("PROGRAMDATA")
    if not base:
        return ""
    p=pathlib.Path(base)/"BybitClusterGrid"/"secrets"/"node.credential"
    try:
        return p.read_text(encoding="ascii").strip()
    except OSError:
        return ""
