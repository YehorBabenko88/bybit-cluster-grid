import asyncio
from collections import deque

import psutil


class ProcessLimitError(RuntimeError):
    pass


async def _drain_stream(stream,tail,max_bytes=8192):
    """Continuously drain a child pipe while retaining only a bounded diagnostic tail."""
    while True:
        chunk=await stream.read(4096)
        if not chunk:return
        tail.append(chunk)
        total=sum(len(x) for x in tail)
        while tail and total>max_bytes:
            overflow=total-max_bytes
            first=tail.popleft()
            if len(first)>overflow:
                tail.appendleft(first[overflow:])
                total=max_bytes
            else:
                total-=len(first)


def _tail_bytes(parts,max_bytes=8192):
    data=b"".join(parts)
    return data[-max_bytes:]


async def terminate_process_tree(proc,grace_seconds=5):
    """Best-effort terminate -> kill for a subprocess and all descendants."""
    try:
        parent=psutil.Process(proc.pid)
        children=parent.children(recursive=True)
    except psutil.Error:
        children=[]
    # Kill descendants even when the direct child already exited: native ML
    # libraries or helper processes must never survive a cancelled lease.
    for child in reversed(children):
        try: child.terminate()
        except psutil.Error: pass
    if proc.returncode is None:
        try: proc.terminate()
        except ProcessLookupError: pass
    try:
        if proc.returncode is None:
            await asyncio.wait_for(proc.wait(),timeout=max(0.1,float(grace_seconds)))
        if children:
            await asyncio.to_thread(psutil.wait_procs,children,timeout=max(0.1,float(grace_seconds)))
    except asyncio.TimeoutError:
        pass
    survivors=[]
    for child in children:
        try:
            if child.is_running(): survivors.append(child)
        except psutil.Error: pass
    for child in survivors:
        try: child.kill()
        except psutil.Error: pass
    if proc.returncode is None:
        try: proc.kill()
        except ProcessLookupError: pass
        await proc.wait()
    if survivors:
        await asyncio.to_thread(psutil.wait_procs,survivors,timeout=max(0.1,float(grace_seconds)))


async def run_supervised_process(argv,*,timeout_seconds,ram_limit_mb=None,
                                 poll_seconds=.5,grace_seconds=5,
                                 env=None,cwd=None):
    """Run heavy compute in a child process with polled RAM/time limits and bounded output."""
    if not argv:
        raise ValueError("argv is required")
    if float(timeout_seconds)<=0:
        raise ValueError("timeout_seconds must be positive")
    if ram_limit_mb is not None and float(ram_limit_mb)<=0:
        raise ValueError("ram_limit_mb must be positive")
    proc=await asyncio.create_subprocess_exec(
        *[str(x) for x in argv],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,cwd=cwd,
    )
    stdout_tail=deque();stderr_tail=deque()
    drains=[
        asyncio.create_task(_drain_stream(proc.stdout,stdout_tail)),
        asyncio.create_task(_drain_stream(proc.stderr,stderr_tail)),
    ]
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
        await asyncio.gather(*drains)
        if proc.returncode!=0:
            tail=_tail_bytes(stderr_tail).decode("utf-8","replace")[-4000:]
            raise RuntimeError(f"ML subprocess exited {proc.returncode}: {tail}")
        return _tail_bytes(stdout_tail)
    except asyncio.CancelledError:
        await terminate_process_tree(proc,grace_seconds)
        raise
    except Exception:
        await terminate_process_tree(proc,grace_seconds)
        raise
    finally:
        for task in drains:
            if not task.done():task.cancel()
        await asyncio.gather(*drains,return_exceptions=True)
