"""One-shot, read-only commissioning checks. Never starts runtime or migrates SQL.

Output contains stable diagnostic codes, never exception messages, DSNs, child
stdout/stderr, environment values or HTTP bodies. Exit 2 means blocked.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SHA = re.compile(r'[0-9a-f]{40}\Z')
QUIESCENT = {'INFRA_ONLY', 'PAUSED', 'STOPPED'}
TABLES = ('schema_migrations', 'collection_ownership', 'collection_ingest_receipts',
          'grid_runtime_state', 'retention_runs', 'analysis_watermarks',
          'retention_consumers', 'consumer_watermarks', 'retention_holds')
COLUMNS = {
    ('retention_runs', 'dataset'): 'text', ('retention_runs', 'status'): 'text',
    ('retention_runs', 'deleted_rows'): 'int8', ('retention_runs', 'details'): 'jsonb',
    ('analysis_watermarks', 'analyzed_through'): 'timestamptz',
    ('collection_ownership', 'generation'): 'int8', ('collection_ownership', 'session'): 'uuid',
    ('collection_ownership', 'lease_until'): 'timestamptz',
    ('collection_ingest_receipts', 'sha256'): 'text', ('collection_ingest_receipts', 'payload'): 'jsonb',
    ('collection_ingest_receipts', 'disposition'): 'text',
    ('consumer_watermarks', 'consumed_through'): 'timestamptz',
    ('retention_consumers', 'required'): 'bool', ('retention_consumers', 'active'): 'bool',
    ('retention_holds', 'expires_at'): 'timestamptz', ('grid_runtime_state', 'state'): 'text',
}


def blocked(code): return {'status': 'BLOCKED', 'code': code}
def safe_failure(code, exc):
    return {**blocked(code), 'error_type': type(exc).__name__}


def physical(path):
    # Windows junctions and POSIX symlinks, including ancestors.
    for p in (path, *path.parents):
        if p.is_symlink() or (p.exists() and getattr(p.stat(follow_symlinks=False), 'st_file_attributes', 0) & 1024):
            return False
    return True


def validate_release(root, expected, role='CONTROL'):
    try:
        deadline = time.monotonic() + 60
        root = Path(root).absolute()
        if not isinstance(expected, str) or not SHA.fullmatch(expected) or not physical(root):
            return blocked('RELEASE_IDENTITY_INVALID')
        mp = root / 'release-manifest.json'
        if not physical(mp): return blocked('RELEASE_PATH_REDIRECTED')
        if mp.stat().st_size > 32 * 1024**2: return blocked('RELEASE_MANIFEST_TOO_LARGE')
        m = json.loads(mp.read_text(encoding='utf-8-sig'))
        if m.get('version') != expected or not isinstance(m.get('files'), dict):
            return blocked('RELEASE_IDENTITY_INVALID')
        names = set()
        for name, digest in m['files'].items():
            if time.monotonic() >= deadline: return blocked('RELEASE_CHECK_TIMEOUT')
            if not isinstance(name, str) or not isinstance(digest, str): return blocked('RELEASE_MANIFEST_INVALID')
            w = PureWindowsPath(name)
            if w.is_absolute() or w.drive or '..' in w.parts or '\\' in name or ':' in name or not re.fullmatch('[0-9a-fA-F]{64}', digest):
                return blocked('RELEASE_MANIFEST_INVALID')
            if name.casefold() in names: return blocked('RELEASE_MANIFEST_INVALID')
            names.add(name.casefold())
            p = root / name
            if not p.is_file() or not p.resolve().is_relative_to(root.resolve()) or not physical(p):
                return blocked('RELEASE_PATH_INVALID')
            h = hashlib.sha256()
            with p.open('rb') as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b''):
                    if time.monotonic() >= deadline: return blocked('RELEASE_CHECK_TIMEOUT')
                    h.update(chunk)
            if h.hexdigest() != digest.lower(): return blocked('RELEASE_HASH_MISMATCH')
        required = {'run_coordinator.py' if role == 'CONTROL' else 'run_worker.py',
                    'grid/control_runtime.py', 'grid/collection_ownership.py', 'grid/retention.py'}
        if not required <= set(m['files']): return blocked('RELEASE_PROTOCOL_FILES_MISSING')
        for p in root.rglob('*.py'):
            if time.monotonic() >= deadline: return blocked('RELEASE_CHECK_TIMEOUT')
            if p.relative_to(root).as_posix() not in m['files']: return blocked('RELEASE_SOURCE_UNVERIFIED')
        return {'status': 'PASS', 'code': 'RELEASE_VERIFIED', 'version': expected}
    except Exception as exc: return safe_failure('RELEASE_UNAVAILABLE', exc)


def check_dependencies():
    if sys.version_info[:2] not in {(3, 11), (3, 12)}: return blocked('PYTHON_VERSION_UNTESTED')
    commands = [[sys.executable, '-I', '-B', '-m', 'pip', 'check'],
                [sys.executable, '-I', '-B', '-c',
                 'import aiohttp,asyncpg,psutil,websockets,pydantic,pydantic_settings,fastapi,uvicorn,httpx,dotenv']]
    try:
        for cmd in commands:
            r = subprocess.run(cmd, capture_output=True, timeout=60, check=False)
            if r.returncode: return blocked('DEPENDENCY_CHECK_FAILED')
        return {'status': 'PASS', 'code': 'DEPENDENCIES_READY', 'python': '.'.join(map(str, sys.version_info[:3]))}
    except Exception as exc: return safe_failure('DEPENDENCY_CHECK_FAILED', exc)


async def database_status(c, expected_database):
    # No DDL/DML, even if application-role credentials were supplied.
    async with c.transaction(readonly=True):
        if await c.fetchval('SELECT current_database()') != expected_database:
            return blocked('DATABASE_IDENTITY_MISMATCH')
        for name in TABLES:
            if await c.fetchval('SELECT to_regclass($1)', name) is None:
                return blocked('GRID_SCHEMA_INCOMPLETE')
        from grid.migrations import MIGRATIONS
        rows = await c.fetch('SELECT version,name FROM schema_migrations')
        if {r['version']: r['name'] for r in rows} != {v: n for v, n, _ in MIGRATIONS}:
            return blocked('MIGRATION_CATALOGUE_MISMATCH')
        state = await c.fetchval('SELECT state FROM grid_runtime_state WHERE singleton=true')
        if state not in QUIESCENT: return blocked('RUNTIME_NOT_QUIESCENT')
        columns = await c.fetch('''SELECT table_name,column_name,udt_name FROM information_schema.columns
            WHERE table_schema=current_schema() AND table_name=ANY($1::text[])''', list(TABLES))
        actual = {(r['table_name'], r['column_name']): r['udt_name'] for r in columns}
        if any(actual.get(key) != kind for key, kind in COLUMNS.items()):
            return blocked('GRID_COLUMNS_INCOMPLETE')
        return {'status': 'PASS', 'code': 'DATABASE_READY', 'migration': 47, 'runtime_state': state}


async def probe_database(dsn):
    c = None
    try:
        u = urlsplit(dsn)
        if u.scheme not in {'postgres', 'postgresql'} or u.path != '/bybit_cluster_grid':
            return blocked('DATABASE_IDENTITY_MISMATCH')
        import asyncpg
        c = await asyncpg.connect(dsn, timeout=5, command_timeout=5, server_settings={
            'default_transaction_read_only': 'on', 'statement_timeout': '5000',
            'lock_timeout': '1000', 'search_path': 'public', 'application_name': 'grid-readonly-preflight'})
        return await database_status(c, 'bybit_cluster_grid')
    except Exception as exc: return safe_failure('DATABASE_UNAVAILABLE', exc)
    finally:
        if c is not None: await c.close(timeout=5)


async def smoke(url):
    try:
        u = urlsplit(url)
        if u.scheme not in {'http', 'https'} or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in {'', '/'}:
            return blocked('SMOKE_URL_INVALID')
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5), trust_env=False) as session:
            async with session.get(url.rstrip('/') + '/health', allow_redirects=False) as r:
                if r.status != 200: return blocked('CONTROL_NOT_READY')
                if r.content_length is not None and r.content_length > 16384: return blocked('CONTROL_REPLY_INVALID')
                raw = await r.content.read(16385)
                if len(raw) > 16384: return blocked('CONTROL_REPLY_INVALID')
                data = json.loads(raw)
                if data.get('ok') is not True or data.get('service') != 'Bybit Cluster Grid Coordinator' or data.get('runtime_state') not in QUIESCENT:
                    return blocked('CONTROL_NOT_QUIESCENT')
                if data.get('control_leader') is not True: return blocked('CONTROL_NOT_LEADER')
                return {'status': 'PASS', 'code': 'CONTROL_QUIESCENT_LEADER'}
    except Exception as exc: return safe_failure('CONTROL_UNAVAILABLE', exc)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release-dir', required=True, type=Path)
    p.add_argument('--expected-sha', required=True)
    p.add_argument('--role', choices=['CONTROL', 'WORKER'], default='CONTROL')
    p.add_argument('--env-file', type=Path)
    p.add_argument('--check-db', action='store_true')
    p.add_argument('--smoke-url')
    p.add_argument('--min-free-gb', type=float, default=35)
    args = p.parse_args(argv)
    checks = {'release': validate_release(args.release_dir, args.expected_sha, args.role),
              'dependencies': check_dependencies()}
    try:
        from dotenv import dotenv_values
        env = dict(os.environ)
        if args.env_file:
            if not args.env_file.is_file(): raise FileNotFoundError()
            env.update(dotenv_values(args.env_file, interpolate=False))
        credential = 'GRID_SHARED_TOKEN' if args.role == 'CONTROL' else 'NODE_CREDENTIAL'
        checks['credentials'] = ({'status': 'PASS', 'code': 'ROLE_CREDENTIAL_PRESENT'}
            if str(env.get(credential) or '').strip() else blocked('ROLE_CREDENTIAL_MISSING'))
        checks['telegram'] = (blocked('TELEGRAM_CONFIGURED') if env.get('TELEGRAM_BOT_TOKEN') else {'status': 'PASS', 'code': 'TELEGRAM_DISABLED'})
        checks['retention'] = ({'status': 'PASS', 'code': 'RETENTION_DISABLED_FOR_COMMISSIONING'}
            if str(env.get('RETENTION_ENABLED', '')).lower() in {'false', '0', 'no', 'off'}
            else blocked('RETENTION_DISABLE_REQUIRED'))
        checks['trading'] = (blocked('TRADING_CREDENTIALS_PRESENT')
            if env.get('BYBIT_API_KEY') or env.get('BYBIT_API_SECRET') else {'status': 'PASS', 'code': 'NO_TRADING_CREDENTIALS'})
        free = shutil.disk_usage(args.release_dir).free / 1024**3
        checks['disk'] = ({'status': 'PASS', 'code': 'DISK_HEADROOM_READY'}
            if 0 < args.min_free_gb < float('inf') and free >= args.min_free_gb else blocked('DISK_HEADROOM_LOW'))
        if args.check_db:
            checks['database'] = asyncio.run(probe_database(env.get('POSTGRES_DSN') or ''))
        if args.smoke_url: checks['control'] = asyncio.run(smoke(args.smoke_url))
    except Exception as exc: checks['configuration'] = safe_failure('CONFIGURATION_UNAVAILABLE', exc)
    # Untested DB must never be mistaken for activation permission.
    result = {'schema': 1, 'mode': 'read-only', 'activation_authorized': False,
              'database_checked': args.check_db, 'checks': checks}
    result['status'] = 'PASS' if all(c['status'] == 'PASS' for c in checks.values()) else 'BLOCKED'
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    sys.exit(main())
