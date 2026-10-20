"""One-time lossless reconciliation of legacy path-normalized RC inventory."""
import contextlib,io,json,os,pathlib,pytest
ROOT=pathlib.Path(__file__).resolve().parents[1]
def main():
    os.chdir(ROOT);os.environ['GRID_REQUIRE_TEST_ATTESTATION']='1'
    old=json.loads((ROOT/'independent_audit/evidence/inventory.json').read_text());nodes=[]
    class Capture:
        def pytest_collection_finish(self,session):nodes.extend(i.nodeid for i in session.items)
    with contextlib.redirect_stdout(io.StringIO()):
        result=pytest.main(['--collect-only','-q','-p','no:cacheprovider',*old['files']],plugins=[Capture()])
    assert int(result)==0 and len(nodes)==739
    legacy=[n.replace(chr(92),'/') for n in nodes]
    assert legacy==old['nodes'] and len(set(legacy))==739
    lookup=dict(zip(legacy,nodes))
    former=json.loads((ROOT/'independent_audit/evidence/former10-inventory.json').read_text())
    value=dict(files=old['files'],nodes=nodes,former10=[lookup[n] for n in former])
    (ROOT/'independent_audit/publication_inventory.json').write_text(json.dumps(value,indent=2),encoding='utf8')
    print('Raw739 and former10: bijective legacy reconciliation PASS')
if __name__=='__main__':main()
