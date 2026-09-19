from grid.archive_disk_budget import archive_allowed,DiskBudget
def test_absurd_archive_size_is_rejected_before_download(tmp_path):
    ok,why=archive_allowed(tmp_path,10*1024**3,DiskBudget(max_single_archive_gb=1,min_free_gb=0,reserve_ratio=0))
    assert not ok and why["reason"]=="archive_too_large"
