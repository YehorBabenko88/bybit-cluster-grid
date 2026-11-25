"""Read-only disposable historical snapshots; no original stores are used."""
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest

from market_data.sqlite_history import HistoricalMarketReader


class FrozenSQLiteTests(unittest.TestCase):
    def test_readonly_aggregate_delta_uses_canonical_decimal_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'aggregates.db'
            connection = sqlite3.connect(source)
            try:
                connection.execute('CREATE TABLE public_trade_aggregates '
                    '(symbol,timeframe,open_time,buy_volume,sell_volume,turnover,trade_count,vwap,max_trade)')
                connection.execute("INSERT INTO public_trade_aggregates VALUES('BTCUSDT','1m',60000,0.3,0.1,1,2,1,1)")
                connection.commit()
            finally:
                connection.close()
            original = source.read_bytes()
            reader = HistoricalMarketReader.open_snapshot(source)
            try:
                rows = list(reader.iter_public_trade_aggregates('BTCUSDT'))
                self.assertEqual(rows[0]['delta'], 0.2)
            finally:
                reader.close()
            self.assertEqual(source.read_bytes(), original)

    def test_legacy_and_current_candles_remain_original_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            for legacy in (False, True):
                with self.subTest(legacy=legacy):
                    source = Path(directory) / ('legacy.db' if legacy else 'current.db')
                    connection = sqlite3.connect(source)
                    try:
                        if legacy:
                            connection.execute('CREATE TABLE candles(symbol,ts,open,high,low,close,volume,turnover)')
                            connection.execute("INSERT INTO candles VALUES('BTCUSDT',60000,1,3,1,2,4,8)")
                        else:
                            connection.execute('CREATE TABLE candles(symbol,timeframe,open_time,open,high,low,close,volume,turnover,complete)')
                            connection.execute("INSERT INTO candles VALUES('BTCUSDT','1m',60000,1,3,1,2,4,8,1)")
                            connection.execute("INSERT INTO candles VALUES('BTCUSDT','1m',120000,2,4,2,3,4,12,0)")
                        connection.commit()
                    finally:
                        connection.close()
                    original = sha256(source.read_bytes()).digest()
                    reader = HistoricalMarketReader.open_snapshot(source)
                    try:
                        rows = list(reader.iter_candles('BTCUSDT'))
                        self.assertEqual(len(rows), 1)
                        self.assertEqual((rows[0].open_time, rows[0].close, rows[0].volume), (60000, 2, 4))
                        self.assertEqual(reader.coverage('BTCUSDT').count, 1)
                        self.assertEqual(reader.coverage('BTCUSDT', dataset='funding').count, 0)
                        with self.assertRaises(sqlite3.OperationalError):
                            reader.connection.execute('DELETE FROM candles')
                    finally:
                        reader.close()
                    self.assertEqual(sha256(source.read_bytes()).digest(), original)
                    self.assertEqual(sorted(p.name for p in source.parent.glob(source.name + '*')), [source.name])

    def test_uncheckpointed_backup_and_missing_source_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'snapshot.db'
            with self.assertRaises(FileNotFoundError):
                HistoricalMarketReader.open_snapshot(source)
            source.write_bytes(b'not a database')
            source.with_name(source.name + '-wal').write_bytes(b'pending')
            with self.assertRaisesRegex(ValueError, 'frozen checkpointed'):
                HistoricalMarketReader.open_snapshot(source)
