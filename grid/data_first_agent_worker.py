"""Dedicated DataFirst route; process provisioning is deliberately fail closed.

A request cannot supply a launcher or select an executable. Until the protected
runtime supplies a reviewed supervised-process adapter, no job is claimed here.
"""
async def run_once(client,*,process_launcher=None):
    if process_launcher is None:
        return {'state':'BLOCKED_PROCESS_LAUNCHER_UNAVAILABLE','claimed':False}
    # The operator-owned adapter must use ml_process_supervisor and preserve
    # its whole-process cleanup; asyncio.to_thread cancellation is insufficient.
    job=await client.claim()
    if job is None:return {'state':'IDLE','claimed':False}
    if job.get('job_type')!='stratt_data_first_v1':raise ValueError('wrong dedicated worker kind')
    from .ml_remote_lease import run_remote_lease
    return await run_remote_lease(client,job,lambda:process_launcher.run_supervised(job,client))
