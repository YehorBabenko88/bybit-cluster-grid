"""Read-only frozen historical SQLite rows; no bootstrap, writer or simulation."""
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from .numeric_dto import volume_delta



@dataclass(frozen=True)
class TimeRange:
    start: int
    end: int

@dataclass(frozen=True)
class Coverage:
    earliest: int | None
    latest: int | None
    count: int
    gaps: tuple[TimeRange, ...] = ()

@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float | None = None
    complete: bool = True


class HistoricalMarketReader:
    def __init__(self,path: Path,connection: sqlite3.Connection,*,read_only=True):
        if read_only is not True:
            raise ValueError("historical snapshot is read only")
        self.path=Path(path); self.connection=connection
        self._read_only=read_only
        cols={r[1] for r in connection.execute('PRAGMA table_info(candles)')}
        self._legacy_candles='ts' in cols and 'open_time' not in cols
        self._historical_tables = (
            {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if read_only else None
        )

    @classmethod
    def open_snapshot(cls, path: Path):
        path = Path(path).resolve(strict=True)
        if any(path.with_name(path.name + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("a frozen checkpointed SQLite backup is required")
        connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        connection.execute("PRAGMA query_only=ON")
        try:
            return cls(path, connection, read_only=True)
        except BaseException:
            connection.close()
            raise

    def close(self):
        self.connection.close()

    def iter_public_trade_aggregates(self,symbol:str,timeframe:str='1m',start_ms:int|None=None,end_ms:int|None=None):
        if self._historical_tables is not None and 'public_trade_aggregates' not in self._historical_tables:
            return
        where=['symbol=?','timeframe=?']; params=[symbol,timeframe]
        if start_ms is not None:
            where.append('open_time>=?'); params.append(int(start_ms))
        if end_ms is not None:
            where.append('open_time<=?'); params.append(int(end_ms))
        cur=self.connection.execute(
            f"SELECT open_time,buy_volume,sell_volume,turnover,trade_count,vwap,max_trade FROM public_trade_aggregates WHERE {' AND '.join(where)} ORDER BY open_time",
            tuple(params))
        for ts,buy,sell,turnover,count,vwap,max_trade in cur:
            yield {'t':ts,'open_time':ts,'buy_volume':buy,'sell_volume':sell,'delta':volume_delta(buy,sell),
                   'turnover':turnover,'trade_count':count,'vwap':vwap,'max_trade':max_trade}

    def coverage(self,symbol:str,dataset:str='candles',timeframe:str='1m',step_ms:int=60_000,start_ms:int|None=None,end_ms:int|None=None)->Coverage:
        mapping={
            'candles':('candles','open_time',True),
            'mark_price':('mark_prices','open_time',True),
            'index_price':('index_prices','open_time',True),
            'premium_index':('premium_index','open_time',True),
            'open_interest':('open_interest','open_time',True),
            'funding':('funding','funding_time',False),
            'long_short_ratio':('long_short_ratio','open_time',True),
            'public_trades':('public_trade_aggregates','open_time',True),
            'public_trade_aggregates':('public_trade_aggregates','open_time',True),
        }
        if dataset not in mapping: raise ValueError('unsupported dataset')
        if dataset=='candles' and self._legacy_candles:
            if timeframe!='1m': return Coverage(None,None,0,())
            where=['symbol=?']; params=[symbol]
            if start_ms is not None:
                where.append('ts>=?'); params.append(int(start_ms))
            if end_ms is not None:
                where.append('ts<=?'); params.append(int(end_ms))
            rows=self.connection.execute(f"SELECT ts FROM candles WHERE {' AND '.join(where)} ORDER BY ts",tuple(params)).fetchall()
            if not rows:return Coverage(None,None,0,())
            times=[r[0] for r in rows]; gaps=[]
            for a,b in zip(times,times[1:]):
                if b-a>step_ms:gaps.append(TimeRange(a+step_ms,b-step_ms))
            return Coverage(times[0],times[-1],len(times),tuple(gaps))
        table,time_col,uses_tf=mapping[dataset]
        if self._historical_tables is not None and table not in self._historical_tables:
            return Coverage(None,None,0,())
        where=['symbol=?']; params=[symbol]
        if dataset in ('candles','mark_price','index_price','premium_index','open_interest'):
            where.append('complete=1')
        if uses_tf:
            where.append('timeframe=?'); params.append(timeframe)
        if start_ms is not None:
            where.append(f'{time_col}>=?'); params.append(int(start_ms))
        if end_ms is not None:
            where.append(f'{time_col}<=?'); params.append(int(end_ms))
        rows=self.connection.execute(
            f"SELECT {time_col} FROM {table} WHERE {' AND '.join(where)} ORDER BY {time_col}",
            tuple(params)).fetchall()
        if not rows:return Coverage(None,None,0,())
        times=[r[0] for r in rows]; gaps=[]
        for a,b in zip(times,times[1:]):
            if b-a>step_ms:gaps.append(TimeRange(a+step_ms,b-step_ms))
        return Coverage(times[0],times[-1],len(times),tuple(gaps))

    def iter_candles(self,symbol:str,timeframe:str='1m',batch_size:int=20_000,start_ms:int|None=None,end_ms:int|None=None):
        time_col='ts' if self._legacy_candles else 'open_time'
        if self._legacy_candles and timeframe!='1m': return
        where=['symbol=?']; params=[symbol]
        if not self._legacy_candles:
            where.append('timeframe=?'); params.append(timeframe)
            where.append('complete=1')
        if start_ms is not None:
            where.append(f'{time_col}>=?'); params.append(int(start_ms))
        if end_ms is not None:
            where.append(f'{time_col}<=?'); params.append(int(end_ms))
        if self._legacy_candles:
            select='symbol,ts,open,high,low,close,volume,turnover'
        else:
            select='symbol,timeframe,open_time,open,high,low,close,volume,turnover,complete'
        cur=self.connection.execute(f"SELECT {select} FROM candles WHERE {' AND '.join(where)} ORDER BY {time_col}",tuple(params))
        while True:
            batch=cur.fetchmany(batch_size)
            if not batch: break
            for r in batch:
                if self._legacy_candles:
                    yield Candle(r[0],'1m',r[1],r[2],r[3],r[4],r[5],r[6],r[7],True)
                else:
                    yield Candle(*r[:-1],complete=bool(r[-1]))
