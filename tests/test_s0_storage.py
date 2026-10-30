import json,pytest
from s0_smoke.storage import Journal,write_new,read_small,request_stop,stop_requested
CTX=dict(head='a'*40,run_id='11111111-1111-4111-8111-111111111111',role='LS5')
def test_chain_and_no_overwrite(tmp_path):
 with Journal(tmp_path,'events.jsonl',CTX,limit=4096) as j:j.add('start',{'ok':True});j.add('end',{})
 rows=[json.loads(x) for x in (tmp_path/'events.jsonl').read_text().splitlines()]
 assert rows[0]['seq']==1 and rows[1]['previous']==rows[0]['sha256']
 with pytest.raises((FileExistsError,ValueError)):Journal(tmp_path,'events.jsonl',CTX)
def test_bounded_append(tmp_path):
 with Journal(tmp_path,'events.jsonl',CTX,limit=100) as j:
  with pytest.raises(ValueError):j.add('event',{'body':'x'*200})
 assert (tmp_path/'events.jsonl').stat().st_size==0
@pytest.mark.parametrize('name',['../foreign','x/y','x:y','CON','NUL','x.'])
def test_leaf_only(tmp_path,name):
 with pytest.raises(ValueError):write_new(tmp_path,name,b'no')
def test_stop_only_own_existing_slot(tmp_path):
 with pytest.raises(FileNotFoundError):request_stop(tmp_path,CTX)
 write_new(tmp_path,'stop.json',json.dumps(dict(CTX,stop=False)).encode())
 assert not stop_requested(tmp_path,CTX)
 request_stop(tmp_path,CTX);assert stop_requested(tmp_path,CTX)
 with pytest.raises(ValueError):request_stop(tmp_path,dict(CTX,head='b'*40))
def test_corrupt_stop_fails_closed(tmp_path):
 write_new(tmp_path,'stop.json',b'not-json')
 with pytest.raises(ValueError):stop_requested(tmp_path,CTX)
def test_missing_stop_fails_closed(tmp_path):
 with pytest.raises(FileNotFoundError):stop_requested(tmp_path,CTX)
