"""One explicit market-data service entry point; no host/process management."""
import argparse
import asyncio
import json
import os


async def _capture(args):
    from .capture_store import CaptureStore
    from .collector import PublicTradeCollector
    sink = await CaptureStore.open(os.environ['MARKET_DATA_INGEST_DSN'],
                                   expected_database=args.database)
    try:
        return await PublicTradeCollector(sink, symbol=args.symbol,
            source_revision=args.source_revision, max_frames=args.max_frames).run()
    finally:
        await sink.close()


async def _backfill(args):
    import asyncpg
    from .capture_store import _WRITER_LOCK
    from .market_backfill import seed_backfill, run_backfill_worker
    pool = await asyncpg.create_pool(os.environ['MARKET_DATA_INGEST_DSN'], min_size=1, max_size=2)
    try:
        async with pool.acquire() as guard:
            if await guard.fetchval('SELECT current_database()') != args.database:
                raise ValueError('backfill database identity mismatch')
            if await guard.fetchval('SELECT pg_try_advisory_lock($1)', _WRITER_LOCK) is not True:
                raise RuntimeError('market data writer already active')
            try:
                # Existing reviewed schema must be provisioned by Unified;
                # this command never bootstraps or migrates an arbitrary DB.
                await seed_backfill(pool, args.symbols.split(','))
                return await run_backfill_worker(pool, 'https://api.bybit.com', max_pages=args.max_pages)
            finally:
                await guard.fetchval('SELECT pg_advisory_unlock($1)', _WRITER_LOCK)
    finally:
        await pool.close()


def main(argv=None, *, startup_admission=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('serve', help='loopback read-only history API')
    capture = commands.add_parser('capture', help='bounded original public trade payload capture')
    capture.add_argument('--symbol', required=True)
    capture.add_argument('--database', required=True)
    capture.add_argument('--source-revision', required=True)
    capture.add_argument('--max-frames', type=int, choices=range(1, 5), default=4)
    backfill = commands.add_parser('backfill', help='bounded public REST history into prepared dedicated schema')
    backfill.add_argument('--symbols', required=True)
    backfill.add_argument('--database', required=True)
    backfill.add_argument('--max-pages', type=int, choices=range(1, 51), default=5)
    args = parser.parse_args(argv)
    if args.command == 'serve':
        from .history_api import main as serve
        return serve(startup_admission=startup_admission)
    if os.environ.get('UNIFIED_MODULE_ID') is not None:
        raise RuntimeError('managed profile permits only the read API')
    result = asyncio.run(_capture(args) if args.command == 'capture' else _backfill(args))
    print(json.dumps(result, default=str, sort_keys=True))


if __name__ == '__main__':
    main()
