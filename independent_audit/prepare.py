"""Extract pinned sources and compose identical/nonoverlapping blobs. No git merge."""
import hashlib, io, itertools, json, pathlib, subprocess, zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE='5d18b2810a8b1b22ce59e46334d35e07f55c46c7'
HEADS={'204':'4dcf0dafba4872cce9b5b14745da3471b8aba67a','205':'c97873fbfc1aefc2996688f93564ea0e98259ee7','206':'ed95dbffb71664a22b34e876c9c4da741201a5d0','207':'c12812ba240a27095d0b01d453b25c1653110276','209':'44de8b2efc9d82d641c79be33a051fbe557d3b5a'}
def git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+str(ROOT),*args],cwd=ROOT)
def extract(sha,dest):
    dest.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(git('archive','--format=zip',sha))) as z:
        for name in z.namelist():
            assert not name.startswith('/') and '..' not in pathlib.PurePosixPath(name).parts
        z.extractall(dest)
def main():
    out=ROOT/'scratch_five';out.mkdir(exist_ok=True)
    changed={pr:git('diff','--name-only',BASE,sha).decode().splitlines() for pr,sha in HEADS.items()}
    overlap=[]
    for a,b in itertools.combinations(HEADS,2):
        for path in sorted(set(changed[a])&set(changed[b])):
            ba=git('show',HEADS[a]+':'+path);bb=git('show',HEADS[b]+':'+path)
            overlap.append(dict(prs=[a,b],path=path,identical=ba==bb,sha256_a=hashlib.sha256(ba).hexdigest(),sha256_b=hashlib.sha256(bb).hexdigest()))
    assert all(x['identical'] for x in overlap),'Differing blob collision: do not overwrite'
    extract(BASE,out/'combined')
    for pr,sha in HEADS.items():
        extract(sha,out/('pr'+pr))
        for path in changed[pr]:
            dest=out/'combined'/path;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(git('show',sha+':'+path))
    report=dict(base=BASE,heads=HEADS,changed=changed,overlap=overlap)
    (out/'composition.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
