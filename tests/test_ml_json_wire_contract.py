import asyncio
import hashlib
import json

import pytest
from grid import ml_transport
from grid.ml_dataset_builder import _canonical
from grid.ml_training_worker import TrainingWorker


SAMPLE = {"sample_id": "1", "symbol": "BTCUSDT", "event_ts": 2,
          "feature_ts": 1, "features": '{"x": 1}', "instrument_features": '{}',
          "target": '{"ret": 0.1}', "quality_status": "GOOD", "split_group": "a",
          "label_end_ts": 3}
RAW = _canonical(SAMPLE)
HASH = hashlib.sha256(RAW.encode()).hexdigest()


class Pool:
    def __init__(self, payload=None, sample=RAW, digest=HASH):
        self.payload = json.dumps({"dataset_id": "dataset"}) if payload is None else payload
        self.sample = sample
        self.digest = digest
        self.writes = []
    async def fetchrow(self, sql, *args):
        if "ml_jobs" in sql:
            return {"payload": self.payload}
        return {"id": "dataset", "sample_count": 1, "feature_version": "1",
                "dataset_hash": hashlib.sha256(self.digest.encode()).hexdigest()}
    async def fetch(self, sql, *args):
        return [{"ordinal": 0, "payload": self.sample, "payload_hash": self.digest}]
    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "UPDATE 1"


def test_claim_decodes_default_asyncpg_job_payload():
    job = ml_transport._public_job({"payload": json.dumps({"dataset_id": "dataset"})})
    assert job["payload"] == {"dataset_id": "dataset"}


@pytest.mark.parametrize("as_mapping", [False, True])
def test_dataset_page_preserves_builder_hash(as_mapping):
    pool = Pool(sample=json.loads(RAW) if as_mapping else RAW)
    page = asyncio.run(ml_transport.dataset_page(pool, "job", "node", 1))
    assert page["samples"][0]["payload"] == json.loads(RAW)
    assert page["samples"][0]["payload_hash"] == HASH


@pytest.mark.parametrize("bad", ['[]', 'null', '1', '"value"', '{invalid', [], None])
def test_claim_rejects_non_object_payload(bad):
    with pytest.raises(ValueError):
        ml_transport._public_job({"payload": bad})


@pytest.mark.parametrize("sample", [RAW, json.loads(RAW)])
def test_training_decodes_before_hash_and_backend(monkeypatch, sample):
    from grid import ml_training_worker
    expected = json.loads(RAW)
    monkeypatch.setattr(ml_training_worker, "walk_forward", lambda rows: [(rows, rows)])
    class Backend:
        def fit(self, rows, parameters):
            assert rows == [expected]
            return rows
        def predict(self, model, rows): return [0]
        def evaluate(self, rows, prediction, **kwargs): return {"score": 1}
        async def serialize(self, model): return "artifact"
    pool = Pool(sample=sample)
    result = asyncio.run(TrainingWorker(pool, Backend(), "test").train("dataset"))
    assert result["folds"] == 1
    assert len(pool.writes) == 1


@pytest.mark.parametrize("bad", ['[]', 'null', '{invalid'])
def test_training_rejects_bad_samples_before_backend(bad):
    pool = Pool(sample=bad, digest=hashlib.sha256(json.dumps(json.loads(bad)).encode()).hexdigest()
                if bad != '{invalid' else HASH)
    with pytest.raises(ValueError):
        asyncio.run(TrainingWorker(pool, object(), "test").train("dataset"))
    assert not pool.writes


def test_training_rejects_tampered_payload():
    pool = Pool(sample=json.dumps(dict(json.loads(RAW), symbol="ETHUSDT")))
    with pytest.raises(ValueError, match="payload hash mismatch"):
        asyncio.run(TrainingWorker(pool, object(), "test").train("dataset"))
    assert not pool.writes


def test_finalize_decodes_job_payload_before_transaction():
    class Context:
        def __init__(self, value): self.value = value
        async def __aenter__(self): return self.value
        async def __aexit__(self, *args): return False
    class FinalizePool(Pool):
        def acquire(self): return Context(self)
        def transaction(self): return Context(self)
        async def fetchrow(self, sql, *args):
            if "ml_artifacts" in sql: return {"id": args[0]}
            return await super().fetchrow(sql, *args)
    pool = FinalizePool()
    result = asyncio.run(ml_transport.finalize_model(pool, "job", "node", 1, "artifact"))
    assert result["model_id"]
    registry = next(args for sql, args in pool.writes if "INSERT INTO model_registry" in sql)
    assert registry[2] == "dataset"


@pytest.mark.parametrize("bad", ['[]', 'null', '{invalid'])
def test_dataset_page_rejects_non_object_samples(bad):
    pool = Pool(sample=bad)
    with pytest.raises(ValueError):
        asyncio.run(ml_transport.dataset_page(pool, "job", "node", 1))
