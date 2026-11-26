"""Bounded rejection must precede input-sized key allocation."""
import builtins,json,pathlib,copy,tracemalloc
import pytest
from market_data import paper_inputs as m

@pytest.mark.parametrize('which',['packet','request','base_request','availability','row','context','evidence','proof'])
def test_wrong_closed_map_cardinality_never_builds_input_sized_set(monkeypatch,which):
    packet=json.loads((pathlib.Path(__file__).parent/'fixtures/paper-inputs-v2-structural.json').read_text())
    huge={str(i):None for i in range(10000)};visited=[]
    def tracked(value=()):
        if type(value) is dict and len(value)>64:visited.append(len(value))
        return builtins.set(value)
    monkeypatch.setattr(m,'set',tracked,raising=False)
    if which=='packet':operation=lambda:m._validate_paper_inputs(huge)
    elif which=='request':operation=lambda:m._paper_request(huge)
    elif which=='base_request':operation=lambda:m._request(huge)
    elif which in ('availability','row'):
        if which=='availability':packet['availability']=huge
        else:packet['rows']=[huge]
        operation=lambda:m._validate_paper_inputs(packet)
    elif which=='context':
        payload=copy.deepcopy(packet['rows'][0]['payload']);payload['_producer_connection']=huge
        row=packet['rows'][0];operation=lambda:m._paper_payload(row['event_type'],payload,packet['request'],int(row['event_us']),int(row['ingest_us']))
    else:
        payload=dict(funding_rate='0.0001')
        payload['_field_observations']=huge if which=='evidence' else dict(schema='market_data.ticker-field-observations.v1',clock_basis='EXCHANGE_FRAME_TS_AND_PROCESS_WALL_CLOCK',fields=dict(funding_rate=huge))
        operation=lambda:m._paper_payload('derivatives_ticker',payload,packet['request'],1000000,1000000)
    with pytest.raises(m.ExportBlocked):operation()
    assert visited==[],f'unbounded key-set allocation before refusal: {visited}'

def test_large_invalid_packet_rejection_transient_allocation_is_bounded():
    huge={str(i):None for i in range(100000)}
    tracemalloc.start()
    try:
        with pytest.raises(m.ExportBlocked):m.validate_paper_inputs(huge)
        _,peak=tracemalloc.get_traced_memory()
    finally:tracemalloc.stop()
    assert peak<256*1024
