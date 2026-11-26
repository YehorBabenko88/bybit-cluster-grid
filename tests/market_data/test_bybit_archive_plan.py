# Source Meta82 test_bybit_archive_plan.py; canonical import transfer.
from datetime import date

import pytest

from market_data.bybit_archive_plan import archive_url, plan_archive_days


def test_futures_and_spot_paths():
    day = date(2025, 1, 9)
    assert archive_url("BTCUSDT", day) == (
        "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-09.csv.gz")
    assert archive_url("BTCUSDT", day, "spot") == (
        "https://public.bybit.com/spot/BTCUSDT/BTCUSDT_2025-01-09.csv.gz")


def test_planner_excludes_unfinished_current_day():
    days = plan_archive_days("ETHUSDT", date(2025, 1, 1), date(2025, 1, 4),
                             today=date(2025, 1, 5))
    assert len(days) == 3
    assert days[-1].day == date(2025, 1, 3)


def test_rejects_bad_symbol_and_unbounded_future_plan():
    with pytest.raises(ValueError):
        archive_url("../BTCUSDT", date(2025, 1, 1))
    with pytest.raises(ValueError):
        plan_archive_days("BTCUSDT", date(2025, 1, 1), date(2025, 1, 10),
                          today=date(2025, 1, 5))
    with pytest.raises(ValueError):
        plan_archive_days("BTCUSDT", date(2025, 1, 1), date(2025, 1, 10),
                          today=date(2025, 1, 20), max_days=3)
