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
