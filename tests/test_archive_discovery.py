from grid.archive_discovery import parse_archive_dates,archive_url
def test_parse_bybit_directory_listing_extracts_only_symbol_daily_archives():
    html='''<a href="BTCUSDT2025-01-01.csv.gz">a</a>
    <a href="BTCUSDT2025-01-02.csv.gz">b</a><a href="ETHUSDT2025-01-01.csv.gz">x</a>'''
    d=parse_archive_dates("BTCUSDT",html)
    assert [x.isoformat() for x in d]==["2025-01-01","2025-01-02"]
    assert archive_url("https://public.bybit.com/trading","BTCUSDT",d[0]).endswith("/BTCUSDT/BTCUSDT2025-01-01.csv.gz")
