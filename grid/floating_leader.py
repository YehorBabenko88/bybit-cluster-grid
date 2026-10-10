import asyncio,hashlib,logging,socket,time
log=logging.getLogger("leader_election")

class FloatingLeader:
    """DB-backed lease election. Any healthy node may own the control plane."""
    def __init__(self,pool,node_id=None,lease_seconds=20,renew_seconds=5):
        self.pool=pool; self.node_id=node_id or socket.gethostname()
        self.lease_seconds=int(lease_seconds); self.renew_seconds=float(renew_seconds)
        self.is_leader=False; self.epoch=None; self.stop_event=asyncio.Event()

    async def campaign(self):
        async with self.pool.acquire() as c:
            async with c.transaction():
                row=await c.fetchrow("""SELECT owner,lease_until,metadata FROM service_leases
                  WHERE service_key='control-plane-leader' FOR UPDATE""")
                if row and row["lease_until"] and row["lease_until"]>await c.fetchval("SELECT now()"):
                    self.is_leader=False; return False
                # Even the same node_id cannot seize an unexpired lease.\n                # A second process must wait for expiry, not steal ownership.\n                previous_epoch = int((row["metadata"] or {}).get("epoch", 0)) if row else 0
                epoch=max(int(time.time()*1000),previous_epoch+1)
                await c.execute("""INSERT INTO service_leases(service_key,owner,lease_until,heartbeat_at,metadata)
                  VALUES('control-plane-leader',$1,now()+($2*interval '1 second'),now(),jsonb_build_object('epoch',$3))
                  ON CONFLICT(service_key) DO UPDATE SET owner=EXCLUDED.owner,lease_until=EXCLUDED.lease_until,
                  heartbeat_at=now(),metadata=EXCLUDED.metadata""",self.node_id,self.lease_seconds,epoch)
        # Leadership becomes visible only after transaction commit succeeds.
        self.epoch=epoch; self.is_leader=True
        return True

    async def renew(self):
        if not self.is_leader:return False
        r=await self.pool.execute("""UPDATE service_leases SET lease_until=now()+($3*interval '1 second'),
          heartbeat_at=now() WHERE service_key='control-plane-leader' AND owner=$1
          AND (metadata->>'epoch')::bigint=$2 AND lease_until>=now()""",
          self.node_id,self.epoch,self.lease_seconds)
        self.is_leader=r.endswith(" 1")
        if not self.is_leader:
            self.epoch=None
        return self.is_leader

    async def run(self,on_gain=None,on_loss=None):
        previous=False
        while not self.stop_event.is_set():
            try:
                current=await (self.renew() if self.is_leader else self.campaign())
            except asyncio.CancelledError:
                raise
            except Exception:
                # Loss of the shared lease store must fail closed immediately.
                # Do not let a transient PostgreSQL outage kill the election loop:
                # clear local leadership and keep campaigning after the normal
                # renewal interval so recovery is automatic when DB returns.
                log.exception("leader election database operation failed",
                              extra={"event":"leader_db_error","node_id":self.node_id})
                current=False
                self.is_leader=False
                self.epoch=None
            if current and not previous and on_gain: await on_gain(self.epoch)
            if previous and not current and on_loss: await on_loss()
            previous=current
            try: await asyncio.wait_for(self.stop_event.wait(),timeout=self.renew_seconds)
            except asyncio.TimeoutError: pass

    def stop(self):self.stop_event.set()
