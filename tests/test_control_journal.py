import tempfile,os
from grid.local_control_journal import LocalControlJournal

def test_local_control_journal_is_monotonic_and_checksummed():
    with tempfile.TemporaryDirectory() as d:
        p=os.path.join(d,"control.json");j=LocalControlJournal(p)
        assert j.apply(1,{"telegram_cursor":{"value":{"next_update_id":7}}})
        assert not j.apply(1,{"telegram_cursor":{"value":{"next_update_id":1}}})
        assert j.load()["state"]["telegram_cursor"]["value"]["next_update_id"]==7
        open(p,"w",encoding="utf8").write('{"version":2,"state":{},"checksum":"bad"}')
        try:j.load();assert False
        except ValueError:pass


def test_stale_temp_files_are_removed_on_start(tmp_path):
    from grid.local_control_journal import LocalControlJournal
    target=tmp_path/"control-state.json"
    stale=tmp_path/"control-state.json.crashed.tmp"
    stale.write_text("partial",encoding="utf-8")
    LocalControlJournal(target)
    assert not stale.exists()
