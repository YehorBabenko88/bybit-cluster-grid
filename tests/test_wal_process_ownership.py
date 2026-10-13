import asyncio
import os
from pathlib import Path
import subprocess
import sys
import threading,time,signal

import pytest

from grid.segment_wal import SegmentWAL

ROOT=Path(__file__).resolve().parents[1]


def child(root):
    code="""import sys
from grid.segment_wal import SegmentWAL
try:
 w=SegmentWAL(sys.argv[1]); print('OPENED',flush=True)
except RuntimeError:
 print('LOCKED',flush=True)
"""
    return subprocess.run([sys.executable,'-c',code,str(root)],cwd=ROOT,capture_output=True,text=True,timeout=10,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def test_other_process_cannot_even_recover_or_repair_owned_wal(tmp_path):
    wal=SegmentWAL(tmp_path)
    result=child(tmp_path)
    assert result.returncode==0
    assert result.stdout.strip()=='LOCKED'


def test_same_process_handles_do_not_allocate_duplicate_ids(tmp_path):
    async def run():
        first=SegmentWAL(tmp_path);second=SegmentWAL(tmp_path)
        ids=await asyncio.gather(first.append({'n':1}),second.append({'n':2}))
        assert sorted(ids)==[1,2]
        assert [rid for rid,_ in first.recover()]==[1,2]
    asyncio.run(run())


def test_crash_releases_os_lock_and_preserves_committed_append(tmp_path):
    code="""import asyncio,sys,time
from grid.segment_wal import SegmentWAL
w=SegmentWAL(sys.argv[1]);asyncio.run(w.append({'durable':1}))
print('READY',flush=True)
sys.stdin.readline()
"""
    process=subprocess.Popen([sys.executable,'-u','-c',code,str(tmp_path)],cwd=ROOT,
                             stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        assert process.stdout.readline().strip()=='READY'
        assert child(tmp_path).stdout.strip()=='LOCKED'
        process.kill();process.wait(timeout=10)
        restarted=SegmentWAL(tmp_path)
        assert restarted.recover()==[(1,{'durable':1})]
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=10)


def test_uncertain_append_fault_blocks_id_reuse_until_recovery(tmp_path,monkeypatch):
    async def run():
        wal=SegmentWAL(tmp_path)
        fsync=os.fsync
        def fail(fd):raise OSError('synthetic fsync failure')
        monkeypatch.setattr(os,'fsync',fail)
        with pytest.raises(OSError):await wal.append({'n':1})
        monkeypatch.setattr(os,'fsync',fsync)
        with pytest.raises(RuntimeError):await wal.append({'n':2})
        wal.close()
        restarted=SegmentWAL(tmp_path)
        assert await restarted.append({'n':2})==2
        assert restarted.recover()==[(1,{'n':1}),(2,{'n':2})]
    asyncio.run(run())


def test_duplicate_crc_valid_record_ids_fail_closed(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path)
        await wal.append({'n':1})
        path=wal._segments()[0]
        with path.open('ab') as handle:handle.write(path.read_bytes())
        with pytest.raises(RuntimeError):wal.recover()
    asyncio.run(run())


def test_recovery_waits_for_partial_write_in_other_thread(tmp_path,monkeypatch):
    import builtins
    wal=SegmentWAL(tmp_path);entered=threading.Event();resume=threading.Event();result=[]
    original=builtins.open
    class SplitFile:
        def __init__(self,handle):self.handle=handle
        def __enter__(self):return self
        def __exit__(self,*args):return self.handle.__exit__(*args)
        def __getattr__(self,name):return getattr(self.handle,name)
        def write(self,data):
            self.handle.write(data[:len(data)//2]);self.handle.flush();entered.set()
            assert resume.wait(5)
            return self.handle.write(data[len(data)//2:])
    def opened(path,mode='r',*args,**kwargs):
        handle=original(path,mode,*args,**kwargs)
        return SplitFile(handle) if mode=='ab' and str(path).endswith('.seg') else handle
    monkeypatch.setattr(builtins,'open',opened)
    writer=threading.Thread(target=lambda:asyncio.run(wal.append({'n':1})))
    def recover():
        try:result.append(wal.recover())
        except BaseException as exc:result.append(exc)
    reader=threading.Thread(target=recover)
    writer.start();assert entered.wait(5);reader.start()
    try:
        time.sleep(.05)
        assert reader.is_alive(),'recovery read uncommitted partial bytes'
    finally:
        resume.set();writer.join(5);reader.join(5)
    assert result==[[(1,{'n':1})]]


def test_close_invalidates_active_recovery_iterator(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path)
        await wal.append({'n':1});await wal.append({'n':2})
        records=wal.iter_recover();assert next(records)[0]==1
        wal.close()
        with pytest.raises(RuntimeError):next(records)
        assert child(tmp_path).stdout.strip()=='OPENED'
    asyncio.run(run())


@pytest.mark.skipif(not hasattr(os,'fork'),reason='POSIX fork only')
def test_fork_child_cannot_retain_dead_parent_wal_lock(tmp_path):
    code="""import os,sys,time
from grid.segment_wal import SegmentWAL
w=SegmentWAL(sys.argv[1]);pid=os.fork()
if pid==0:
 time.sleep(30);os._exit(0)
print(pid,flush=True);sys.stdin.readline()
"""
    process=subprocess.Popen([sys.executable,'-u','-c',code,str(tmp_path)],cwd=ROOT,
                             stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    descendant=None
    try:
        descendant=int(process.stdout.readline().strip())
        process.kill();process.wait(timeout=5)
        assert child(tmp_path).stdout.strip()=='OPENED'
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=5)
        if descendant:
            try:os.kill(descendant,signal.SIGKILL)
            except ProcessLookupError:pass
