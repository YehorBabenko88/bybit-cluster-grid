# Source Meta82 test_archive_url_hardening.py; canonical import transfer.
import pytest

from market_data.bybit_archive_download import validate_archive_url


@pytest.mark.parametrize("url", [
    "https://public.bybit.com/trading/../BTCUSDT/BTCUSDT2025-01-01.csv.gz",
    "https://public.bybit.com/trading/%2e%2e/BTCUSDT2025-01-01.csv.gz",
    "https://public.bybit.com/trading/BTCUSDT%2fother/BTCUSDT2025-01-01.csv.gz",
    "https://public.bybit.com/trading/BTCUSDT/ETHUSDT2025-01-01.csv.gz",
    "https://public.bybit.com/trading/BTCUSDT//BTCUSDT2025-01-01.csv.gz",
    "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz/extra",
    "https://public.bybit.com/trading/BTCUSDT/BTCUSDT%2e.csv.gz",
])
def test_reject_ambiguous_archive_urls(url):
    with pytest.raises(ValueError):
        validate_archive_url(url)


@pytest.mark.parametrize("url", [
    "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz",
    "https://public.bybit.com/spot/BTCUSDT/BTCUSDT_2025-01-01.csv.gz",
])
def test_accept_expected_archive_urls(url):
    validate_archive_url(url)
