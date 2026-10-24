"""Independent read-only check of freshly downloaded PR227 artifacts.

Usage: python tools/verify_pr227_original_evidence.py runtime-directory staging-directory
Downloads are not executed. SHA256 verifies receipt payloads and Git blobs, not
the download ZIP or the trustworthiness of the hosted runner itself.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

SHA='da69209af86567232fb3038a899580fe2e061a0b'
ROOT=Path(__file__).resolve().parents[1]


@lru_cache(None)
def blob(name):
    return subprocess.check_output(['git','show',SHA+':'+name],cwd=ROOT)


def main(directories):
    mapping={'ddl-offline':'ddl_offline_inventory.json','ddl-pg18':'ddl_pg18_inventory.json',
             'staging-offline':'protected_staging_inventory.json',
             'staging-baseline':'protected_staging_baseline_inventory.json',
             'pc4-pg18-plan':'pc4_pg18_plan_inventory.json'}
    counts=[]; sources=set(); artifacts=files=0
    for directory in directories:
        for folder in Path(directory).iterdir():
            artifacts+=1;files+=len(list(folder.iterdir()))
            manifest=json.loads(next(folder.glob('*sha256.json')).read_text(encoding='utf-8-sig'))
            assert manifest['sha']==SHA
            for name,digest in manifest['files'].items():
                if isinstance(digest,dict):
                    if 'git_blob_sha256' in digest:
                        assert hashlib.sha256(blob(name)).hexdigest()==digest['git_blob_sha256'];sources.add(name)
                    else:
                        assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest['working_bytes_sha256']
                else:
                    data=(folder/name).read_bytes() if (folder/name).exists() else blob(name)
                    assert hashlib.sha256(data).hexdigest()==digest
                    if not (folder/name).exists():sources.add(name)
            for xml in folder.glob('*.xml'):
                tree=ET.parse(xml)
                assert all(int(s.get(k,0))==0 for s in tree.iter('testsuite') for k in ('errors','failures','skipped'))
                events=json.loads((folder/(xml.stem+'-events.json')).read_text(encoding='utf-8-sig'))
                inv=json.loads(blob('tests/fixtures/'+mapping[xml.stem]))
                nodes=events.get('collected',events.get('nodes'))
                passed=events.get('passed',events.get('calls'))
                bad=events.get('bad',events.get('bad_reports'))
                assert events['sha']==SHA and bad==[] and nodes==inv['nodes']==sorted(passed)
                cases=sorted([c.get('classname'),c.get('name')] for c in tree.iter('testcase'))
                assert cases==inv['junit_cases']
                counts.append({'artifact':folder.name,'suite':xml.stem,'tests':len(cases)})
    assert artifacts==9 and files==49
    print(json.dumps({'sha':SHA,'artifacts':artifacts,'files':files,
                      'source_blobs':len(sources),'suites':counts},indent=2))


if __name__=='__main__':
    assert len(sys.argv)==3
    main(sys.argv[1:])
