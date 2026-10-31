"""Bounded scheduling and conservative backup retention; no host deletion.

Returned expired IDs are proposals. A storage backend must independently ensure
no active restore, pinned release or PITR chain references them before removal.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Backup:
    identity: str
    completed_at: int
    manifest_verified: bool
    restore_verified: bool

    def __post_init__(self):
        if (type(self.identity) is not str or not self.identity or len(self.identity) > 128
                or type(self.completed_at) is not int or self.completed_at < 0
                or type(self.manifest_verified) is not bool or type(self.restore_verified) is not bool
                or self.restore_verified and not self.manifest_verified):
            raise ValueError('invalid backup evidence')


class BackupPolicy:
    def __init__(self, interval_seconds, retain):
        if type(interval_seconds) is not int or not 60 <= interval_seconds <= 604800:
            raise ValueError('backup interval must be 60s..7d')
        if type(retain) is not int or not 1 <= retain <= 10000:
            raise ValueError('retention bound')
        self.interval, self.retain = interval_seconds, retain

    def due(self, now, last_completed):
        if any(type(v) is not int or v < 0 for v in (now, last_completed)) or now < last_completed:
            raise ValueError('invalid backup clock')
        return now - last_completed >= self.interval

    @staticmethod
    def restore_verified(manifest_ok, wal_contiguous, application_checks_ok):
        return all(value is True for value in (manifest_ok, wal_contiguous, application_checks_ok))

    def expired(self, backups, required_pitr_bases):
        if not isinstance(backups, list) or len(backups) > 10000 or any(not isinstance(b, Backup) for b in backups):
            raise ValueError('bounded backup inventory required')
        ids = {b.identity for b in backups}
        if len(ids) != len(backups) or not isinstance(required_pitr_bases, set) or not required_pitr_bases <= ids:
            raise ValueError('backup chain inventory invalid')
        verified = sorted((b for b in backups if b.restore_verified), key=lambda b: (b.completed_at, b.identity), reverse=True)
        protected = {b.identity for b in verified[:self.retain]} | required_pitr_bases
        # Never delete unverified backups automatically, nor the only restored copy.
        return sorted(b.identity for b in verified if b.identity not in protected)


class BackupScheduler:
    """One bounded scheduled cycle; runtime persists returned evidence/last clock.

    create performs basebackup + WAL collection, verify_manifest uses
    pg_verifybackup, verify_restore restores to an isolated database and checks
    WAL continuity plus application invariants. Never infer restore from exit0
    of the backup process alone. Failed/unverified backups remain retained.
    """
    def __init__(self, policy, create, verify_manifest, verify_restore, timeout=3600):
        import asyncio
        if not isinstance(policy, BackupPolicy) or not all(callable(f) for f in (create,verify_manifest,verify_restore)):
            raise ValueError('backup policy and verification adapters required')
        if type(timeout) is not int or not 1 <= timeout <= 86400:
            raise ValueError('bounded backup timeout required')
        self.policy,self.create,self.manifest,self.restore,self.timeout=policy,create,verify_manifest,verify_restore,timeout
        self.lock=asyncio.Lock()

    async def run_due(self, now, last_completed):
        import asyncio
        if not self.policy.due(now,last_completed):
            return None
        async with self.lock:
            identity=await asyncio.wait_for(self.create(),self.timeout)
            manifest=await asyncio.wait_for(self.manifest(identity),self.timeout) is True
            restored=manifest and await asyncio.wait_for(self.restore(identity),self.timeout) is True
            return Backup(identity,now,manifest,restored)
