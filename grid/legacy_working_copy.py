import sqlite3
from pathlib import Path

def create_working_copy(source,destination):
    src=Path(source);dst=Path(destination)
    dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists():return str(dst)
    s=sqlite3.connect(f"file:{src.resolve().as_posix()}?mode=ro",uri=True)
    d=sqlite3.connect(str(dst))
    try:
        s.backup(d,pages=8192)
        chk=d.execute("PRAGMA quick_check").fetchone()[0]
        if str(chk).lower()!="ok":raise RuntimeError(f"working copy quick_check failed: {chk}")
    finally:
        d.close();s.close()
    return str(dst)
