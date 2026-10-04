from __future__ import annotations
import os,pathlib


def _root():
    return pathlib.Path(os.environ.get("ProgramData",r"C:\ProgramData"))/"BybitClusterGrid"


def compute_locally_enabled():
    root=_root()
    return not (root/"operator.stop").exists() and not (root/"bootstrap.pause").exists()
