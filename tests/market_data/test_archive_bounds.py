"""Canonical archive boundary regressions, fake session and temporary paths only."""
from datetime import date, datetime, timezone
import pytest
from market_data.archive_resume import ResumeState, resume_headers
from market_data.bybit_archive_download import download_archive
from market_data.archive_resumable_download import download_resumable
from market_data.bybit_archive_plan import plan_archive_days, archive_url
from market_data.history_parallel import bounded_map

@pytest.mark.parametrize('offset,total',[(True,10),(1.0,10),(1,True),(1,10.0),(1,2_000_000_001)])
def test_resume_rejects_noninteger_or_excessive_state(offset,total):
    with pytest.raises(ValueError):resume_headers(ResumeState(offset,'"v1"',total))

@pytest.mark.asyncio
@pytest.mark.parametrize('budget',[True,False,1.5,float('nan'),float('inf'),2_000_000_001])
@pytest.mark.parametrize('downloader',[download_archive,download_resumable])
async def test_invalid_transport_budget_refused_before_any_mutation(tmp_path,budget,downloader):
    class ForbiddenSession:
        def get(self,*args,**kwargs):raise AssertionError('TRANSPORT_MUST_NOT_START')
    target=tmp_path/'not-created'/'archive.csv.gz'
    with pytest.raises(ValueError):await downloader(ForbiddenSession(),'https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz',target,max_bytes=budget)
    assert not target.parent.exists()

@pytest.mark.parametrize('bad',[True,1.5,float('nan'),100_000])
def test_archive_plan_strict_bounded_days(bad):
    with pytest.raises(ValueError):plan_archive_days('BTCUSDT',date(2025,1,1),date(2025,1,2),today=date(2025,1,3),max_days=bad)

def test_archive_plan_requires_utc_calendar_dates_not_datetimes():
    with pytest.raises(ValueError):archive_url('BTCUSDT',datetime(2025,1,1,tzinfo=timezone.utc))

@pytest.mark.asyncio
@pytest.mark.parametrize('bad',[True,1.5,float('nan')])
async def test_parallel_rejects_noninteger_concurrency(bad):
    async def worker(value):raise AssertionError('NO_WORK')
    with pytest.raises(ValueError):await bounded_map([],worker,concurrency=bad)
