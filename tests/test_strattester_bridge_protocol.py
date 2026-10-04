import pytest
from grid.strattester_bridge_protocol import digest,make_manifest,validate_manifest


def test_handoff_is_deterministic_and_tamper_evident():
    cfg={"b":2,"a":1}; spec={"symbol":"BTCUSDT","start":1,"end":2}
    m=make_manifest(run_id="r",job_id="j",job_type="backtest",dataset_hash="d",
      code_version="abc",config=cfg,input_spec=spec,result={"x":1},
      metrics={"accuracy":.51},artifacts=[{"sha256":"z","uri":"artifact://x"}])
    assert m["config_hash"]==digest({"a":1,"b":2})
    assert validate_manifest(m,{"run_id":"r","job_id":"j","dataset_hash":"d",
      "code_version":"abc","config_hash":digest(cfg),"input_hash":digest(spec)})
    bad=dict(m); bad["metrics"]={"accuracy":.99}
    with pytest.raises(ValueError,match="result hash"):
        validate_manifest(bad)


def test_handoff_rejects_wrong_dataset_or_version():
    m=make_manifest(run_id="r",job_id="j",job_type="train",dataset_hash="d",
      code_version="abc",config={},input_spec={},result={})
    with pytest.raises(ValueError,match="dataset_hash mismatch"):
        validate_manifest(m,{"dataset_hash":"other"})
    with pytest.raises(ValueError,match="code_version mismatch"):
        validate_manifest(m,{"code_version":"def"})
