from integration import windows_python_probe as probe

def test_endpoint_failure_does_not_erase_connect_timeout(monkeypatch):
    class Client:
        def gettimeout(self):return 6.0
        def getsockname(self):raise OSError(10022,'synthetic')
    error=dict(kind='TIMEOUT',winerror=None,errno=None)
    monkeypatch.setattr(probe,'socket_trace',lambda *a,**k:(None,error))
    monkeypatch.setattr(probe,'transport_connections',[])
    observed=probe.connect_observation(Client(),4,'127.0.0.1',1234,'listener',dict(transport_nonce='a'*32,parent_pid=12))
    assert observed==error and len(probe.transport_connections)==1
    row=probe.transport_connections[0]
    assert row['kind']=='TIMEOUT' and row['local_host'] is None and row['local_port'] is None
    assert row['local_error']['kind']=='OSERROR' and row['deadline_ms']==6000
