from grid.strattester_bridge_protocol import digest,make_manifest,validate_manifest


def _shard(part):
    spec={"symbol":"BTCUSDT","part":part,"range":[part*100,(part+1)*100]}
    result={"symbol":"BTCUSDT","part":part,"bars":100,"checksum":digest(spec)}
    return make_manifest(run_id="run-1",job_id=f"shard-{part}",job_type="probe",
        dataset_hash="dataset-1",code_version="v1",config={"seed":7},
        input_spec=spec,result=result,metrics={"rows":100})


def test_same_shard_is_byte_deterministic_across_workers():
    a=_shard(1);b=_shard(1)
    assert a==b
    assert a["result_hash"]==b["result_hash"]
    assert validate_manifest(a)


def test_distributed_aggregate_fingerprint_is_order_independent():
    local=[_shard(i) for i in range(4)]
    distributed=[local[2],local[0],local[3],local[1]]
    local_fp=digest(sorted((m["job_id"],m["result_hash"]) for m in local))
    distributed_fp=digest(sorted((m["job_id"],m["result_hash"]) for m in distributed))
    assert local_fp==distributed_fp


def test_one_changed_shard_changes_run_fingerprint():
    manifests=[_shard(i) for i in range(3)]
    baseline=digest(sorted((m["job_id"],m["result_hash"]) for m in manifests))
    changed=dict(manifests[1]);changed["result"]=dict(changed["result"]);changed["result"]["bars"]=99
    changed["result_hash"]=digest({"result":changed["result"],"metrics":changed["metrics"],"artifacts":[]})
    manifests[1]=changed
    after=digest(sorted((m["job_id"],m["result_hash"]) for m in manifests))
    assert baseline!=after
