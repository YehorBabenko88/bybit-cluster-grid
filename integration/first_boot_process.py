"""Owned process lifetime and bounded private control; no arbitrary PID operations."""
import asyncio
import json
import os
from pathlib import Path
import psutil
import secrets
import signal
import sys
from .first_boot_policy import require_ci


class OwnedChild:
    def __init__(self,env,root,label,redactions):
        self.env=env;self.root=Path(root);self.label=label;self.redactions=redactions;self.pending={};self.sequence=0;self.logs=[];self.process=None
        self.env['GRID_FIXTURE_NONCE']=secrets.token_hex(32);self.redactions.add(self.env['GRID_FIXTURE_NONCE'])
        marker={k:self.env[k] for k in ('EXACT_HEAD_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GRID_FIXTURE_NONCE')}
        (self.root/'owned.json').write_text(json.dumps(marker))
    async def start(self):
        require_ci()
        self.ready=asyncio.get_running_loop().create_future()
        self.process=await asyncio.create_subprocess_exec(sys.executable,'-m','integration.first_boot_child',env=self.env,cwd=self.root,
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT,limit=2**20)
        self.created=psutil.Process(self.process.pid).create_time()
        self.reader=asyncio.create_task(self.drain())
        receipt=await asyncio.wait_for(self.ready,20)
        if receipt!={'pid':self.process.pid,'role':self.env['ROLE'],'head':self.env['EXACT_HEAD_SHA']}:raise RuntimeError('CHILD_IDENTITY_MISMATCH')
        return self
    def sanitize(self,text):
        for secret in self.redactions:
            if secret:text=text.replace(secret,'[REDACTED]')
        return text[:12000]
    async def drain(self):
        try:
            while True:
                raw=await self.process.stdout.readline()
                if not raw:break
                text=raw.decode('utf-8','replace').rstrip()
                if text.startswith('FIRST_BOOT_PRIVATE_CONTROL:'):
                    value=json.loads(text.split(':',1)[1])
                    if value.get('nonce')!=self.env['GRID_FIXTURE_NONCE']:raise RuntimeError('PRIVATE_PIPE_NONCE')
                    future=self.ready if value['id']==0 else self.pending.get(value['id'])
                    if future is None or future.done():raise RuntimeError('PRIVATE_PIPE_SEQUENCE')
                    if value['ok']:future.set_result(value['value'])
                    else:future.set_exception(RuntimeError('CHILD_ACTION_REJECTED'))
                elif len(self.logs)<1000:self.logs.append(self.sanitize(text))
        except Exception as exc:
            for f in [self.ready,*self.pending.values()]:
                if not f.done():f.set_exception(RuntimeError('CHILD_PIPE_FAILED'))
            raise
        finally:
            for f in [self.ready,*self.pending.values()]:
                if not f.done():f.set_exception(RuntimeError('CHILD_EXITED_WITHOUT_REPLY'))
    async def command(self,action,node=''):
        self.sequence+=1;sequence=self.sequence;future=asyncio.get_running_loop().create_future();self.pending[sequence]=future
        try:
            self.process.stdin.write((json.dumps(dict(id=sequence,nonce=self.env['GRID_FIXTURE_NONCE'],action=action,node=node))+'\n').encode());await self.process.stdin.drain()
            return await asyncio.wait_for(future,20)
        finally:self.pending.pop(sequence,None)
    def same_process(self):
        if self.process.returncode is not None:return False
        try:
            p=psutil.Process(self.process.pid)
            return p.create_time()==self.created and p.ppid()==os.getpid()
        except psutil.NoSuchProcess:return False
    async def stop(self,crash=False):
        if not self.process:return None
        cooperative_failed=False
        if self.process.returncode is None:
            if not self.same_process():raise RuntimeError('PID_IDENTITY_UNCERTAIN_NO_SIGNAL')
            if not crash and self.env['ROLE']=='coordinator':
                try:await self.command('shutdown')
                except Exception:
                    cooperative_failed=True
                    if self.process.returncode is None:
                        if not self.same_process():raise RuntimeError('PID_IDENTITY_UNCERTAIN_NO_SIGNAL')
                        self.process.send_signal(signal.SIGTERM)
                self.process.stdin.close()
            else:self.process.send_signal(signal.SIGKILL if crash else signal.SIGTERM)
        try:code=await asyncio.wait_for(self.process.wait(),35)
        except TimeoutError:
            if self.same_process():self.process.kill();await self.process.wait()
            raise RuntimeError('CONTROLLED_SHUTDOWN_FAILED')
        if self.process.stdin:self.process.stdin.close()
        await asyncio.wait_for(self.reader,5)
        if cooperative_failed:raise RuntimeError('COOPERATIVE_SHUTDOWN_FAILED')
        if not crash and code!=0:raise RuntimeError('CHILD_EXIT_NONZERO')
        return code


async def stop_all(children):
    errors=[]
    for child in reversed(children):
        try:
            if child.process and child.process.returncode is None:await child.stop()
        except Exception as exc:errors.append(type(exc).__name__)
    if errors or any(c.process and c.process.returncode is None for c in children):
        raise RuntimeError('CHILD_CONTAINMENT_FAILED')
