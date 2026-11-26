"""Literal historical SQLite fixtures ONLY; no account or result-store engine.

Schemas preserve the retained Strattester13998 research/staging layout.
This module is outside the market_data distribution and never runs a strategy.
"""
from contextlib import closing
from pathlib import Path
import json
import sqlite3

LEGACY_FIELDS=(
 'run_id TEXT NOT NULL, symbol TEXT NOT NULL, strategy_id TEXT NOT NULL, '
 'strategy_version TEXT NOT NULL, created_at REAL NOT NULL, metrics TEXT NOT NULL'
)
LEGACY_KEY=', PRIMARY KEY(run_id, symbol, strategy_id, strategy_version)'
PUBLISHED_EXTRA=', job_id TEXT, lease_token INTEGER NOT NULL DEFAULT 0, node_generation INTEGER NOT NULL DEFAULT 0'

def _fresh(path):
 path=Path(path)
 try:path.lstat()
 except FileNotFoundError:return path
 raise FileExistsError('fresh test fixture required')

def legacy_backup(path):
 path=_fresh(path);row=('run','BTCUSDT','legacy','1',123.125,'{"fold":2,"score":NaN}')
 with closing(sqlite3.connect(path)) as db,db:
  db.execute('CREATE TABLE research_results('+LEGACY_FIELDS+LEGACY_KEY+')')
  db.execute('INSERT INTO research_results VALUES (?,?,?,?,?,?)',row)
 return row

def current_backup(path,*,stage=True):
 path=_fresh(path)
 row=('stage','run','BTCUSDT','legacy','1',123.125,json.dumps({'variant':'BASE'},sort_keys=True),'job',7,3)
 with closing(sqlite3.connect(path)) as db,db:
  db.execute('CREATE TABLE research_results('+LEGACY_FIELDS+PUBLISHED_EXTRA+LEGACY_KEY+')')
  db.execute('CREATE TABLE staged_research_results(stage_id TEXT PRIMARY KEY,'+LEGACY_FIELDS+PUBLISHED_EXTRA+')')
  if stage:db.execute('INSERT INTO staged_research_results VALUES (?,?,?,?,?,?,?,?,?,?)',row)
 return row if stage else None
