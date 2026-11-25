from pathlib import Path
from hashlib import sha256
import sqlite3
import pytest
from market_data.history_planning import declare_history_instrument,declared_dataset_requests,plan_history_requests

def _planned(instrument,*,end_ms):
    return plan_history_requests(declare_history_instrument(instrument),end_ms=end_ms).requests

def _legacy(path):
    c=sqlite3.connect(path)
    c.execute('CREATE TABLE candles(symbol TEXT NOT NULL, ts INTEGER NOT NULL, open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL, turnover REAL NOT NULL, PRIMARY KEY(symbol,ts))')
    c.execute("INSERT INTO candles VALUES('BTCUSDT',0,100,101,99,100,1,100)")
    c.commit(); c.close()

def _frozen_current(path,rows=()):
    """Literal private TEST fixture, never a runtime store/bootstrap."""
    if path.exists():raise AssertionError('fresh fixture destination required')
    connection=sqlite3.connect(path)
    try:
        connection.execute('CREATE TABLE candles(symbol TEXT NOT NULL,timeframe TEXT NOT NULL,open_time INTEGER NOT NULL,open REAL NOT NULL,high REAL NOT NULL,low REAL NOT NULL,close REAL NOT NULL,volume REAL NOT NULL,turnover REAL,complete INTEGER NOT NULL,PRIMARY KEY(symbol,timeframe,open_time))')
        connection.executemany('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)',rows)
        connection.commit()
    finally:connection.close()


def test_open_market_store_prefers_existing_local_legacy_data(tmp_path):
    # Retained unmigrated DB role: imports remain local, assertions unchanged.
    from strattester.marketdata.readiness import open_market_store,ensure_history
    from strattester.marketdata.sync_engine import DataRequirement,SyncState
    root=tmp_path/'app'; root.mkdir()
    legacy=tmp_path/'legacy.db'; _legacy(legacy)
    before=legacy.read_bytes()
    opened=open_market_store(root,legacy_paths=(legacy,))
    try:
        assert opened.path==legacy
        assert opened.store.coverage('BTCUSDT','candles','1m').count==1
        assert opened.store.coverage('BTCUSDT','mark_price','1m').count==0
        assert list(opened.store.iter_public_trade_aggregates('BTCUSDT')) == []
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            opened.store.checkpoint_wal()
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            opened.store.connection.execute('DELETE FROM candles')
    finally:
        opened.store.close()
    assert legacy.read_bytes()==before


def test_historical_reader_sees_committed_wal_rows_without_checkpoint(tmp_path):
    # Retained unmigrated DB role: imports remain local, assertions unchanged.
    from strattester.marketdata.readiness import open_market_store,ensure_history
    from strattester.marketdata.sync_engine import DataRequirement,SyncState
    root = tmp_path / 'app'
    root.mkdir()
    legacy = tmp_path / 'legacy #1.sqlite3'
    writer = sqlite3.connect(legacy)
    try:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute('CREATE TABLE candles(symbol, ts, open, high, low, close, volume, turnover)')
        writer.execute("INSERT INTO candles VALUES('BTCUSDT',0,100,101,99,100,1,100)")
        writer.commit()

        def row_digest(connection):
            rows = connection.execute('SELECT * FROM candles ORDER BY symbol, ts').fetchall()
            return sha256(repr(rows).encode()).digest()

        # Initialize SQLite's reader bookkeeping before comparing file bytes.
        from strattester.marketdata.integrity import quick_check
        assert quick_check(legacy).ok
        files = [legacy, Path(f'{legacy}-wal'), Path(f'{legacy}-shm')]
        before = [path.read_bytes() for path in files]
        opened = open_market_store(root, legacy_paths=(legacy,))
        try:
            assert opened.store.coverage('BTCUSDT').count == 1
            assert row_digest(opened.store.connection) == row_digest(writer)
        finally:
            opened.store.close()
        assert [path.read_bytes() for path in files] == before
    finally:
        writer.close()

def test_open_market_store_refuses_creation_without_existing_history(tmp_path,monkeypatch):
    from market_data.sqlite_history import HistoricalMarketReader
    root=tmp_path/'app';root.mkdir();missing=root/'data'/'bybit_1m.sqlite3'
    def forbidden(*args,**kwargs):raise AssertionError('missing source must refuse before SQLite open')
    monkeypatch.setattr(sqlite3,'connect',forbidden)
    # Canonical explicit-source API replaces retired GRID bootstrap/error text.
    with pytest.raises(FileNotFoundError):HistoricalMarketReader.open_snapshot(missing)
    assert not (root/'data'/'bybit_1m.sqlite3').exists()
    assert list(root.iterdir())==[]


def test_ensure_history_refuses_legacy_writer_without_fetch_or_mutation(tmp_path):
    # Retained unmigrated DB role: imports remain local, assertions unchanged.
    from strattester.marketdata.readiness import open_market_store,ensure_history
    from strattester.marketdata.sync_engine import DataRequirement,SyncState
    root = tmp_path / 'app'
    root.mkdir()
    # Existing historical fixture is deliberately created by the TEST only.
    # Runtime open_market_store must not create any market table or new DB.
    from strattester.marketdata.sqlite_store import SQLiteMarketStore
    market_file = root/'data'/'bybit_1m.sqlite3'
    SQLiteMarketStore.open(market_file).close()
    opened = open_market_store(root, legacy_paths=())
    try:
        class ForbiddenClient:
            def fetch_klines(self, *args, **kwargs):
                raise AssertionError('Strattester must not call Bybit')
        req = DataRequirement('BTCUSDT', 'candles', '1m', 0, 60_000)
        before = opened.store.connection.total_changes
        result = ensure_history(opened.store, ForbiddenClient(), (req,))
        assert len(result) == 1
        assert result[0].state is SyncState.REPAIR_REQUIRED
        assert result[0].message == 'GRID_ATTESTED_HISTORY_API_REQUIRED'
        assert opened.store.connection.total_changes == before
        assert opened.store.coverage('BTCUSDT', 'candles', '1m').count == 0
    finally:
        opened.store.close()


def test_existing_candles_not_promoted_to_source_attested(tmp_path,monkeypatch):
    from market_data.sqlite_history import HistoricalMarketReader
    from market_data.history_range_audit import assess_declared_history_range
    import socket
    root=tmp_path/'app';root.mkdir();market_file=root/'historical.sqlite3'
    _frozen_current(market_file,[('BTCUSDT','1m',0,100,101,99,100,1,100,1)])
    original=market_file.read_bytes();original_files=sorted(root.iterdir())
    def forbidden(*args,**kwargs):raise AssertionError('read-only inspection must not fetch')
    monkeypatch.setattr(socket,'socket',forbidden)
    reader=HistoricalMarketReader.open_snapshot(market_file)
    try:
        before=reader.connection.total_changes
        coverage=reader.coverage('BTCUSDT','candles','1m')
        result=assess_declared_history_range(required_start_ms=0,required_end_ms=0,
            available_start_ms=coverage.earliest,available_end_ms=coverage.latest,
            instrument_status='UNKNOWN',recoverable=False)
        # A counted local row is not source-attested readiness or repair authority.
        assert result['readiness']=='NOT_EVALUATED' and result['coverage']=='UNKNOWN'
        assert reader.connection.total_changes==before
        assert reader.coverage('BTCUSDT','candles','1m').count==1
        assert result['range_status']=='BOUNDARIES_PRESENT'
        assert result['source_authenticity']=='NOT_EVALUATED' and result['point_in_time_availability']=='UNKNOWN'
        assert result['execution_authority'] is False and result['trading_authorized'] is False
        with pytest.raises(sqlite3.OperationalError,match='readonly'):reader.connection.execute('DELETE FROM candles')
    finally:reader.close()
    assert market_file.read_bytes()==original and sorted(root.iterdir())==original_files


def test_frozen_empty_history_inspection_is_unqualified_without_fetch_or_mutation(tmp_path,monkeypatch):
    """PARTIAL old ensure_history role: no fabricated batch/repair-result adapter."""
    from market_data.sqlite_history import HistoricalMarketReader
    from market_data.history_range_audit import assess_declared_history_range
    import socket
    source=tmp_path/'empty.sqlite3';_frozen_current(source)
    original=source.read_bytes();original_files=sorted(tmp_path.iterdir())
    def forbidden(*args,**kwargs):raise AssertionError('read-only inspection must not fetch')
    monkeypatch.setattr(socket,'socket',forbidden)
    reader=HistoricalMarketReader.open_snapshot(source)
    try:
        before=reader.connection.total_changes;coverage=reader.coverage('BTCUSDT','candles','1m')
        result=assess_declared_history_range(required_start_ms=0,required_end_ms=60000,
            available_start_ms=coverage.earliest,available_end_ms=coverage.latest,
            instrument_status='UNKNOWN',recoverable=False)
        assert reader.connection.total_changes==before
        assert reader.coverage('BTCUSDT','candles','1m').count==0
        assert result['range_status']=='INSUFFICIENT_RANGE' and result['coverage']=='UNKNOWN'
        assert result['readiness']=='NOT_EVALUATED' and result['source_authenticity']=='NOT_EVALUATED'
        assert result['execution_authority'] is False and result['trading_authorized'] is False
        with pytest.raises(sqlite3.OperationalError,match='readonly'):reader.connection.execute('DELETE FROM candles')
    finally:reader.close()
    assert source.read_bytes()==original and sorted(tmp_path.iterdir())==original_files


def test_requirements_skip_explicitly_unsupported_optional_datasets():
    instrument={"symbol":"NEWUSDT","launchTime":"60000","fundingInterval":None,
                "supportsOpenInterest":False,"supportsFunding":False,"supportsLongShortRatio":False}
    caps=declared_dataset_requests(declare_history_instrument(instrument))
    req=_planned(instrument,end_ms=600000)
    datasets={x.dataset for x in req}
    assert datasets=={"candles","mark_price","index_price","premium_index"}
    assert "open_interest" not in caps and "funding" not in caps

def test_supported_optional_datasets_remain_required():
    instrument={"symbol":"BTCUSDT","launchTime":"0","fundingInterval":"480",
                "supportsOpenInterest":True,"supportsFunding":True,"supportsLongShortRatio":True}
    assert {x.dataset for x in _planned(instrument,end_ms=600000)}=={
        "candles","mark_price","index_price","premium_index","open_interest","funding","long_short_ratio"}


def test_requirements_stop_at_delisting_boundary():
    instrument={"symbol":"OLDUSDT","launchTime":"60000","deliveryTime":"600000",
                "fundingInterval":"480","supportsOpenInterest":True,"supportsFunding":True}
    req=_planned(instrument,end_ms=900000)
    by={x.dataset:x for x in req}
    assert by['candles'].start_ms==60000 and by['candles'].end_ms==600000
    assert by['open_interest'].start_ms==300000 and by['open_interest'].end_ms==600000
    assert 'funding' not in by  # no complete 480m observation exists inside lifetime

def test_requirements_empty_before_instrument_launch():
    instrument={"symbol":"NEWUSDT","launchTime":"600000","fundingInterval":"480"}
    assert _planned(instrument,end_ms=300000)==()

def test_zero_delivery_time_does_not_truncate_perpetual_instrument():
    instrument={"symbol":"BTCUSDT","launchTime":"0","deliveryTime":"0","fundingInterval":"480"}
    req=_planned(instrument,end_ms=900000)
    by={x.dataset:x for x in req}
    assert by['candles'].end_ms==900000
    assert by['open_interest'].end_ms==900000
    assert by['funding'].end_ms==0


def test_dataset_windows_align_to_their_own_sampling_grid():
    instrument={"symbol":"XUSDT","launchTime":"61000","deliveryTime":"899999",
                "fundingInterval":"8","supportsOpenInterest":True,"supportsFunding":True,
                "supportsLongShortRatio":True}
    req={x.dataset:x for x in _planned(instrument,end_ms=999999)}
    assert req['candles'].start_ms==120000 and req['candles'].end_ms==840000
    assert req['open_interest'].start_ms==300000 and req['open_interest'].end_ms==600000
    assert req['long_short_ratio'].start_ms==300000 and req['long_short_ratio'].end_ms==600000
    assert req['funding'].start_ms==480000 and req['funding'].end_ms==480000
