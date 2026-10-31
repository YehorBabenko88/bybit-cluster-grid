import asyncio,hashlib,json,logging,math,socket,time
log=logging.getLogger("leader_election")

class FloatingLeader:
    """DB-backed lease election. Any healthy node may own the control plane."""
    def __init__(self,pool,node_id=None,lease_seconds=20,renew_seconds=5,*,coordination=None,cleanup_timeout_seconds=5):
        self.pool=pool; self.node_id=node_id or socket.gethostname()
        self.coordination=coordination; self.coordination_lease=None; self._coordination_epoch=None
        self.ready=False; self.requires_fencing=False
        self.cleanup_timeout_seconds=float(cleanup_timeout_seconds)
        if not math.isfinite(self.cleanup_timeout_seconds) or self.cleanup_timeout_seconds <= 0:
            raise ValueError('positive cleanup deadline required')
        self.lease_seconds=int(lease_seconds); self.renew_seconds=float(renew_seconds)
        if self.lease_seconds <= 0 or not math.isfinite(self.renew_seconds) or not (0 < self.renew_seconds < self.lease_seconds):
            raise ValueError('leader lease requires 0 < renew_seconds < lease_seconds')
        self.is_leader=False; self.epoch=None; self.stop_event=asyncio.Event()

    async def campaign(self):
        if self.coordination is not None and self.requires_fencing:
            from .coordination import CoordinationLost
            raise CoordinationLost('FENCING_REQUIRED: writer cleanup is unconfirmed')
        if self.coordination is None:
            return await self._campaign_pg()
        self.is_leader=False; self.epoch=None; self.coordination_lease=None
        lease=await self.coordination.acquire(self.node_id)
        if lease is None:return False
        try:
            timeout=getattr(getattr(self.coordination,'config',None),'request_timeout',self.renew_seconds)
            won=await asyncio.wait_for(self._campaign_pg(),timeout=timeout)
            epoch=self.epoch
            # Never expose a committed PG row without the independent session.
            self.is_leader=False; self.epoch=None
            if not won:return False
            if not await self.coordination.validate(lease):
                await self._release_pg(epoch)
                return False
            self.coordination_lease=lease; self._coordination_epoch=epoch
            self.epoch=epoch; self.is_leader=True
            return True
        except BaseException:
            self.is_leader=False; self.epoch=None
            raise
        finally:
            if self.coordination_lease != lease:
                try:await self.coordination.release(lease)
                except Exception:log.exception('failed to release unused DCS session')

    async def renew(self):
        if self.coordination is None:
            return await self._renew_pg()
        if not self.is_leader:return False
        lease=self.coordination_lease
        try:
            if lease is None or not await self.coordination.renew(lease):
                self.is_leader=False; self.epoch=None
                return False
            timeout=getattr(getattr(self.coordination,'config',None),'request_timeout',self.renew_seconds)
            pg_current=await asyncio.wait_for(self._renew_pg(),timeout=timeout)
            if not pg_current or not await self.coordination.validate(lease):
                self.is_leader=False; self.epoch=None
                return False
            return True
        except BaseException:
            self.is_leader=False; self.epoch=None
            raise

    async def release(self, epoch):
        result=await self._release_pg(epoch)
        if self.coordination is not None and self._coordination_epoch == epoch:
            lease=self.coordination_lease
            self.coordination_lease=None; self._coordination_epoch=None
            if lease is not None:await self.coordination.release(lease)
        return result

    async def _campaign_pg(self):
        async with self.pool.acquire() as c:
            async with c.transaction():
                row=await c.fetchrow("""SELECT owner,lease_until,metadata FROM service_leases
                  WHERE service_key='control-plane-leader' FOR UPDATE""")
                if row and row["lease_until"] and row["lease_until"]>await c.fetchval("SELECT now()"):
                    self.is_leader=False
                    self.epoch=None
                    return False
                # Even the same node_id cannot seize an unexpired lease.
                # A second process must wait for expiry, not steal ownership.
                metadata = row["metadata"] if row else None
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                if metadata is not None and not isinstance(metadata, dict):
                    raise ValueError("invalid leader lease metadata: expected object")
                raw_epoch = (metadata or {}).get("epoch", 0)
                if isinstance(raw_epoch, bool) or not isinstance(raw_epoch, int) or raw_epoch < 0:
                    raise ValueError("invalid leader lease epoch: expected nonnegative integer")
                previous_epoch = raw_epoch
                max_epoch = (1 << 63) - 1
                if previous_epoch >= max_epoch:
                    raise ValueError("leader lease epoch exhausted bigint range")
                epoch=max(int(time.time()*1000),previous_epoch+1)
                if epoch > max_epoch:
                    raise ValueError("leader lease epoch exceeds bigint range")
                acquired=await c.fetchval("""INSERT INTO service_leases(service_key,owner,lease_until,heartbeat_at,metadata)
                  VALUES('control-plane-leader',$1,now()+($2*interval '1 second'),now(),jsonb_build_object('epoch',$3::bigint))
                  ON CONFLICT(service_key) DO UPDATE SET owner=EXCLUDED.owner,lease_until=EXCLUDED.lease_until,
                  heartbeat_at=now(),metadata=EXCLUDED.metadata
                  WHERE (service_leases.lease_until IS NULL OR service_leases.lease_until <= now())
                  RETURNING (metadata->>'epoch')::bigint""",self.node_id,self.lease_seconds,epoch)
                # A concurrent first insert can win while we wait on its
                # unique-key lock. Only the successful INSERT/UPDATE returns.

                if acquired is None:
                    self.is_leader=False
                    self.epoch=None
                    return False
        # Leadership becomes visible only after transaction commit succeeds.
        self.epoch=epoch; self.is_leader=True
        return True

    async def _renew_pg(self):
        if not self.is_leader:return False
        r=await self.pool.execute("""UPDATE service_leases SET lease_until=now()+($3*interval '1 second'),
          heartbeat_at=now() WHERE service_key='control-plane-leader' AND owner=$1
          AND (metadata->>'epoch')::bigint=$2 AND lease_until>=now()""",
          self.node_id,self.epoch,self.lease_seconds)
        self.is_leader=r.endswith(" 1")
        if not self.is_leader:
            self.epoch=None
        return self.is_leader

    async def _release_pg(self, epoch):
        """Release only the lease acquired by this exact leadership epoch."""
        return await self.pool.execute("""UPDATE service_leases
          SET lease_until=now(), heartbeat_at=now()
          WHERE service_key='control-plane-leader' AND owner=$1
          AND (metadata->>'epoch')::bigint=$2""", self.node_id, epoch)

    async def run(self,on_gain=None,on_loss=None):
        if self.coordination is None:
            return await self._run_legacy(on_gain,on_loss)
        return await self._run_coordinated(on_gain,on_loss)

    async def _bounded_task_stop(self, task):
        if task is None:return True
        if not task.done():task.cancel()
        done,_=await asyncio.wait({task},timeout=self.cleanup_timeout_seconds)
        if not done:return False
        try:task.result()
        except BaseException:pass
        return True

    async def _cleanup_coordinated(self, initializer, renewer, on_loss, held_epoch, had_initializer):
        self.ready=False; self.is_leader=False; self.epoch=None
        initialized_stopped=await self._bounded_task_stop(initializer)
        renewal_stopped=await self._bounded_task_stop(renewer)
        cleaned=not had_initializer if on_loss is None else False
        if on_loss is not None:
            task=asyncio.create_task(on_loss())
            done,_=await asyncio.wait({task},timeout=self.cleanup_timeout_seconds)
            if done:
                try:cleaned=task.result() is not False
                except BaseException:cleaned=False
            else:task.cancel()
        if not (initialized_stopped and renewal_stopped and cleaned):
            self.requires_fencing=True; self.stop()
            log.error('FENCING_REQUIRED: control writer cleanup not confirmed')
            return False
        try:
            await self.release(held_epoch)
        except Exception:
            # Local writers stopped, but retaining a failed-release lease is
            # conservative. Never advertise readiness while release is unknown.
            log.exception('control lease release failed after confirmed cleanup')
        return True

    async def _run_coordinated(self,on_gain=None,on_loss=None):
        from .coordination import floating_leader_guard
        while not self.stop_event.is_set() and not self.requires_fencing:
            try:
                acquired=await self.campaign()
            except asyncio.CancelledError:
                self.ready=False; self.is_leader=False; self.epoch=None
                self.stop()
                raise
            except Exception:
                self.ready=False; self.is_leader=False; self.epoch=None
                acquired=False
                log.exception('DCS-backed campaign failed closed')
            if not acquired:
                try:await asyncio.wait_for(self.stop_event.wait(),timeout=self.renew_seconds)
                except asyncio.TimeoutError:pass
                continue
            held_epoch=self.epoch
            lost=asyncio.Event()
            async def renew_independently():
                while True:
                    await asyncio.sleep(self.renew_seconds)
                    try:valid=await self.renew()
                    except asyncio.CancelledError:raise
                    except Exception:
                        self.is_leader=False; self.epoch=None; valid=False
                    if not valid:
                        self.ready=False; lost.set(); return
            renewer=asyncio.create_task(renew_independently())
            initializer=asyncio.create_task(on_gain(held_epoch)) if on_gain else None
            loss_wait=asyncio.create_task(lost.wait())
            stop_wait=asyncio.create_task(self.stop_event.wait())
            cancelled=False
            try:
                if initializer is not None:
                    done,_=await asyncio.wait({initializer,loss_wait,stop_wait},return_when=asyncio.FIRST_COMPLETED)
                    if initializer in done:
                        initializer.result()
                    else:
                        continue
                if not lost.is_set() and not self.stop_event.is_set():
                    # Initialization may have crossed a TTL or database epoch.
                    # The same-loop renewer is not an independent host watchdog.
                    await floating_leader_guard(self)()
                    self.ready=True
                    await asyncio.wait({loss_wait,stop_wait},return_when=asyncio.FIRST_COMPLETED)
            except asyncio.CancelledError:
                cancelled=True; self.stop()
            except Exception:
                log.exception('DCS-backed leader initialization/activation failed')
            finally:
                loss_wait.cancel(); stop_wait.cancel()
                await asyncio.gather(loss_wait,stop_wait,return_exceptions=True)
                await self._cleanup_coordinated(initializer,renewer,on_loss,held_epoch,on_gain is not None)
            if cancelled:raise asyncio.CancelledError

    async def _run_legacy(self,on_gain=None,on_loss=None):
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
            # Shutdown can race with an in-flight campaign. Never start
            # leader-only services after stop has already been requested.
            if current and self.stop_event.is_set():
                acquired_epoch = self.epoch
                self.is_leader = False
                self.epoch = None
                current = False
                if acquired_epoch is not None:
                    try:
                        await self.release(acquired_epoch)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        log.exception("failed to release lease after concurrent stop",
                                      extra={"event": "leader_stop_release_failed"})
            if current and not previous and on_gain:
                try:
                    await on_gain(self.epoch)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("leader gain callback failed",extra={"event":"leader_gain_failed"})
                    # A failed initialization must not strand the lease until timeout.
                    # Epoch fencing prevents releasing a lease acquired by a successor.
                    failed_epoch=self.epoch
                    self.is_leader=False
                    self.epoch=None
                    current=False
                    try:
                        if failed_epoch is not None:
                            await self.release(failed_epoch)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        log.exception("failed to release lease after leader initialization error",
                                      extra={"event":"leader_release_failed"})
            if previous and not current and on_loss and not self.stop_event.is_set():
                try:
                    await on_loss()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("leader loss callback failed",extra={"event":"leader_loss_failed"})
            previous=current
            try: await asyncio.wait_for(self.stop_event.wait(),timeout=self.renew_seconds)
            except asyncio.TimeoutError: pass

    def stop(self):self.stop_event.set()

    async def shutdown(self, on_loss=None):
        """Stop local leadership and release only the lease held by this epoch.

        Callers should stop leader-only services before releasing the lease,
        so a successor cannot start while the old services are still running.
        """
        self.stop()
        held_epoch = self.epoch if self.is_leader else None
        self.is_leader = False
        self.epoch = None
        if held_epoch is None:
            return
        # Do not release early when cleanup fails: the lease must remain
        # fenced until expiry rather than overlap a successor with old work.
        if on_loss is not None:
            await on_loss()
        await self.release(held_epoch)

