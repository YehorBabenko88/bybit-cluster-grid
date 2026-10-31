"""Real autocrlf checkout must preserve raw-qualified PostgreSQL examples."""
import os,pathlib,subprocess,sys,tempfile
sys.path.insert(0,os.environ.get('UNIFIED_SOURCE_ROOT',str(pathlib.Path(__file__).resolve().parents[2]/'unified-system')))
from integration.source_guard import SourceFence


def test_postgres_example_survives_real_autocrlf_checkout():
    root=pathlib.Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='mission3-autocrlf-') as temp:
        repo=pathlib.Path(temp)
        def git(*args):return subprocess.check_output(['git','-c','core.hooksPath='+os.devnull,'-C',str(repo),*args],stderr=subprocess.PIPE)
        git('init');git('config','core.autocrlf','false')
        (repo/'.gitattributes').write_bytes((root/'.gitattributes').read_bytes())
        path=repo/'config/ha/postgresql18.conf.example';path.parent.mkdir(parents=True)
        expected=subprocess.check_output(['git','--no-replace-objects','-C',str(root),'cat-file','blob','HEAD:config/ha/postgresql18.conf.example']);path.write_bytes(expected)
        git('add','.');git('-c','user.name=Lab','-c','user.email=lab@example.invalid','commit','-m','source bytes')
        git('config','core.autocrlf','true');path.unlink();git('checkout','HEAD','--','config/ha/postgresql18.conf.example')
        assert path.read_bytes()==expected,'Windows autocrlf changed raw-qualified PostgreSQL config'
        SourceFence(repo).check()
