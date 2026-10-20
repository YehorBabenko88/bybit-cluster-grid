"""One-time review-branch-only job isolation; original PR branches unchanged."""
import pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1]
GUARD="${{ github.head_ref != 'review/offline-rc-20261020' && github.ref_name != 'review/offline-rc-20261020' }}"
def main():
    for p in (ROOT/'.github/workflows').glob('*.yml'):
        if p.name=='offline-rc-review.yml':continue
        text=p.read_text();before,sep,jobs=text.partition('jobs:\n')
        assert sep,p
        assert not re.search(r'^    if:',jobs,re.M),p
        jobs=re.sub(r'^(  [A-Za-z0-9_-]+:\n)',lambda m:m[1]+'    if: '+GUARD+'\n',jobs,flags=re.M)
        p.write_text(before+sep+jobs,encoding='utf8')
if __name__=='__main__':main()
