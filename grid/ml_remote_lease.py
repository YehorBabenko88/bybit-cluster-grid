import asyncio

async def run_remote_lease(client,job,work,renew_every=30):
    task=asyncio.create_task(work())
    try:
        while not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task),timeout=float(renew_every))
            except asyncio.TimeoutError:
                renewed=await client.renew(job)
                if renewed is None:
                    task.cancel()
                    await asyncio.gather(task,return_exceptions=True)
                    raise RuntimeError("remote ML lease lost")
        return await task
    except asyncio.CancelledError:
        task.cancel();await asyncio.gather(task,return_exceptions=True);raise
