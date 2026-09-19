import compileall, pathlib, subprocess, sys

def run_preflight(release_dir):
    root=pathlib.Path(release_dir)
    if not (root/"grid").exists():
        return False,"grid package missing"
    if not compileall.compile_dir(str(root/"grid"),quiet=1,force=True):
        return False,"python compileall failed"
    req=root/"requirements.txt"
    if not req.exists():
        return False,"requirements.txt missing"
    return True,"ok"
