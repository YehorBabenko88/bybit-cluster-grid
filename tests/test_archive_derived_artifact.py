from datetime import datetime,timezone
from grid.archive_derived_artifact import write_derived_artifact,iter_derived_artifact,inspect_derived_artifact


def _rows():
    return [
      {"symbol":"BTCUSDT","ts":datetime(2026,1,1,tzinfo=timezone.utc),
       "open":100.0,"high":102.0,"low":99.0,"close":101.0,
       "buy_volume":3.0,"sell_volume":2.0,"delta":1.0,"trade_count":5,
       "poc_price":100.0,
       "levels":{101.0:{"buy":1.0,"sell":1.0,"buy_count":1,"sell_count":1},
                 100.0:{"buy":2.0,"sell":1.0,"buy_count":2,"sell_count":1}}},
      {"symbol":"BTCUSDT","ts":datetime(2026,1,1,0,1,tzinfo=timezone.utc),
       "open":101.0,"high":103.0,"low":100.0,"close":102.0,
       "buy_volume":4.0,"sell_volume":1.0,"delta":3.0,"trade_count":5,
       "poc_price":102.0,
       "levels":{102.0:{"buy":4.0,"sell":1.0,"buy_count":4,"sell_count":1}}},
    ]


def test_derived_archive_artifact_is_deterministic_and_roundtrips(tmp_path):
    a=tmp_path/"a.gz";b=tmp_path/"b.gz"
    meta={"symbol":"BTCUSDT","archive_date":"2026-01-01","tick_size":0.5}
    x=write_derived_artifact(a,_rows(),meta)
    y=write_derived_artifact(b,_rows(),meta)
    assert x["sha256"]==y["sha256"]
    assert x["source_rows"]==10
    assert x["derived_candles"]==2
    assert x["derived_footprint_rows"]==3
    rows=list(iter_derived_artifact(a,meta))
    assert len(rows)==2
    assert rows[0]["ts"]==datetime(2026,1,1,tzinfo=timezone.utc)
    assert rows[0]["levels"][100.0]["buy"]==2.0


def test_inspection_matches_written_summary(tmp_path):
    path=tmp_path/"derived.gz";meta={"symbol":"BTCUSDT","archive_date":"2026-01-01","tick_size":0.5}
    written=write_derived_artifact(path,_rows(),meta)
    inspected=inspect_derived_artifact(path,meta)
    assert inspected["source_rows"]==written["source_rows"]
    assert inspected["derived_candles"]==written["derived_candles"]
    assert inspected["derived_footprint_rows"]==written["derived_footprint_rows"]
