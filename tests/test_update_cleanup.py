import os
import pathlib
import time
import zipfile

from grid.update_manager import (
    cleanup_release_storage,current_version,previous_version,rollback,switch_current,
)

def _release(root,name):
    p=pathlib.Path(root)/"releases"/name
    p.mkdir(parents=True,exist_ok=True)
    (p/"run_worker.py").write_text("# runnable",encoding="utf-8")
    return p

def test_switch_records_real_previous_and_rollback_uses_it(tmp_path):
    root=tmp_path/"install"
    a=_release(root,"aaaaaaaa")
    b=_release(root,"11111111")
    c=_release(root,"ffffffff")
    switch_current(root,a.name)
    switch_current(root,b.name)
    assert current_version(root)==b.name
    assert previous_version(root)==a.name
    # Lexical/hash order is deliberately unrelated to deployment order.
    assert rollback(root)==a.name
    assert current_version(root)==a.name
    assert previous_version(root)==b.name

def test_cleanup_protects_current_previous_and_recent(tmp_path):
    install=tmp_path/"install"; data=tmp_path/"data"
    names=["old-a","old-b","previous","current"]
    ps={n:_release(install,n) for n in names}
    switch_current(install,"previous")
    switch_current(install,"current")
    old=time.time()-3*86400
    for p in ps.values(): os.utime(p,(old,old))
    result=cleanup_release_storage(install,data,keep_recent=0,older_than_seconds=86400)
    assert (install/"releases"/"current").exists()
    assert (install/"releases"/"previous").exists()
    assert not (install/"releases"/"old-a").exists()
    assert not (install/"releases"/"old-b").exists()
    assert set(result["protected"])=={"current","previous"}

def test_cleanup_removes_only_old_staging_downloads_and_upgrade_workspaces(tmp_path):
    install=tmp_path/"install"; data=tmp_path/"data"
    _release(install,"current"); switch_current(install,"current")
    staging=install/"releases"/"dead.staging"; staging.mkdir()
    downloads=data/"downloads"; downloads.mkdir(parents=True)
    old_zip=downloads/"old.zip"; old_zip.write_bytes(b"x")
    fresh_zip=downloads/"fresh.zip"; fresh_zip.write_bytes(b"x")
    upgrade=data/"upgrade-staging-old"; upgrade.mkdir(parents=True)
    old=time.time()-3*86400
    for p in (staging,old_zip,upgrade): os.utime(p,(old,old))
    result=cleanup_release_storage(install,data,keep_recent=0,older_than_seconds=86400)
    assert not staging.exists()
    assert not old_zip.exists()
    assert fresh_zip.exists()
    assert not upgrade.exists()
    assert result["staging"]==["dead.staging"]
    assert result["downloads"]==["old.zip"]
    assert result["upgrades"]==["upgrade-staging-old"]
