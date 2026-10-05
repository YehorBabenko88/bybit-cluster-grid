import asyncio
import json
import os
import signal
import sys

import psutil


class ProcessLimitError(RuntimeError):
    pass


async def terminate_process_tree(proc,grace_seconds=5):
    """Best-effort terminate -> kill for a subprocess and all descendants."""
    if proc.returncode is not None:
        return
    try:
        parent=psutil.Process(proc.pid)
        children=parent.children(recursive=True)
    except psutil.Error:
        children=[]
    for child in children:
        try: child.terminate()
        except psutil.Error: pass
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(),timeout=max(0.1,float(grace_seconds)))
    except asyncio.TimeoutError:
        for child in children:
            try: child.kill()
            except psutil.Error: pass
        try: proc.kill()
        except ProcessLookupError: pass
        await proc.wait()


async def run_supervised_process(argv,*,timeout_seconds,ram_limit_mb=None,
                                 poll_seconds=.5,grace_seconds=5,
                                 env=None,cwd=None):
    """Run heavy compute out-of-process with hard timeout/RAM containment."""
    if not argv:
        raise ValueError("argv is required")
    proc=await asyncio.create_subprocess_exec(
        *[str(x) for x in argv],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,cwd=cwd,
    )
    started=asyncio.get_running_loop().time()
    try:
        while proc.returncode is None:
            if asyncio.get_running_loop().time()-started > float(timeout_seconds):
                raise ProcessLimitError("ML subprocess timeout exceeded")
            if ram_limit_mb is not None:
                try:
                    root=psutil.Process(proc.pid)
                    rss=root.memory_info().rss
                    for child in root.children(recursive=True):
                        try: rss+=child.memory_info().rss
                        except psutil.Error: pass
                    if rss > int(float(ram_limit_mb)*1024*1024):
                        raise ProcessLimitError("ML subprocess RAM limit exceeded")
                except psutil.NoSuchProcess:
                    pass
            try:
                await asyncio.wait_for(proc.wait(),timeout=max(.05,float(poll_seconds)))
            except asyncio.TimeoutError:
                pass
        stdout,stderr=await proc.communicate()
        if proc.returncode!=0:
            tail=stderr.decode("utf-8","replace")[-2000:]
            raise RuntimeError(f"ML subprocess exited {proc.returncode}: {tail}")
        return stdout
    except asyncio.CancelledError:
        await terminate_process_tree(proc,grace_seconds)
        raise
    except Exception:
        await terminate_process_tree(proc,grace_seconds)
        raise
