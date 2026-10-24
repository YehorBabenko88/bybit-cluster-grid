import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from grid.control_runtime import LeaderFenceError


def test_standalone_archive_refuses_before_bootstrap_or_exchange(monkeypatch):
    from grid import archive_service
    async def forbidden():raise AssertionError('unfenced DB bootstrap attempted')
    monkeypatch.setattr(archive_service,'prepare_database',forbidden)
    with pytest.raises(LeaderFenceError):asyncio.run(archive_service.service_loop())


def test_injected_raw_pool_cannot_enable_archive():
    from grid.archive_service import service_loop
    with pytest.raises(LeaderFenceError):asyncio.run(service_loop(db=SimpleNamespace(pool=object())))


@pytest.mark.parametrize('failed',[False,True])
def test_raw_ml_training_closes_pool_without_masking_result(monkeypatch,failed):
    from grid import ml_compute_entry
    from grid.db import Database
    pool=SimpleNamespace(close=AsyncMock())
    async def connect(self):self.pool=pool
    monkeypatch.setattr(Database,'connect',connect)
    # This unit isolates training cleanup after successful startup validation;
    # real validation and restricted-role startup have separate PG18 tests.
    from grid import service
    monkeypatch.setattr(service,'verify_runtime_schema',AsyncMock())
    monkeypatch.setattr(ml_compute_entry,'TabularBoostBackend',lambda *a,**kw:None)
    monkeypatch.setattr(ml_compute_entry,'LocalArtifactStore',lambda *a:None)
    class Worker:
        def __init__(self,*a,**kw):pass
        async def train(self,*a,**kw):
            if failed:raise ValueError('original training failure')
            return {'model_id':'published'}
    monkeypatch.setattr(ml_compute_entry,'TrainingWorker',Worker)
    async def run():
        job={'id':'job','payload':{'dataset_id':'dataset'},'lease_owner':'node','lease_generation':1}
        if failed:
            with pytest.raises(ValueError,match='original training failure'):await ml_compute_entry.train_job(job)
        else:assert await ml_compute_entry.train_job(job)=={'model_id':'published'}
        pool.close.assert_awaited_once()
    asyncio.run(run())
