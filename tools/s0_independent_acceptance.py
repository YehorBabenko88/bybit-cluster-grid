"""Independent offline hosted-artifact consistency checks. Never permission."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile
import xml.etree.ElementTree as ET

LIMIT = 512 * 1024 * 1024
ENTRY = 64 * 1024 * 1024
COUNT = 20000
REQUIREMENTS_VERSION = 3
REQUIRED_SOURCES = frozenset(('s0_smoke/cli.py','s0_smoke/entry.py','installer/physical-smoke-s0.ps1','installer/physical-smoke-s0/S0Launcher.cs','docs/PHYSICAL_SMOKE_S0.md','installer/physical-smoke-s0/TokenObserver.cs','installer/physical-smoke-s0/S0Bootstrap.cs','installer/physical-smoke-s0/S0Inputs.cs','installer/physical-smoke-s0-bootstrap.ps1','docs/PHYSICAL_SMOKE_S0_BOOTSTRAP_COMMANDS.md','docs/PHYSICAL_SMOKE_S0_INDEPENDENT_ACCEPTANCE.md'))


def need(value):
    if not value:
        raise ValueError('OFFLINE_EVIDENCE_CHECK_BLOCKED')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result)
            result[key] = value
        return result
    need(len(raw) <= ENTRY)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: need(False))


def safe_name(name):
    need(type(name) is str and name and '\\' not in name and ':' not in name)
    need(not name.startswith('/') and all(p not in ('', '.', '..') for p in name.split('/')))
    need(str(PurePosixPath(name)) == name and not any(ord(c) < 32 for c in name))


def archive_members(raw):
    need(type(raw) is bytes and len(raw) <= LIMIT)
    result = {}; folded = set(); total = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist(); need(len(infos) <= COUNT)
        for info in infos:
            safe_name(info.orig_filename)
            need(info.orig_filename == info.filename)
            safe_name(info.filename)
            need(not info.is_dir() and not info.flag_bits & 1)
            mode = info.external_attr >> 16
            need(not stat.S_ISLNK(mode) and (not stat.S_IFMT(mode) or stat.S_ISREG(mode)))
            need(info.filename.casefold() not in folded and info.file_size <= ENTRY)
            folded.add(info.filename.casefold()); total += info.file_size; need(total <= LIMIT)
            with archive.open(info) as stream:
                data = stream.read(ENTRY + 1)
            need(len(data) == info.file_size and len(data) <= ENTRY)
            result[info.filename] = data
    return result


def check_context(record, expected):
    need(type(record) is dict and all(type(record.get(k)) is str and record[k] == v for k,v in expected.items()))


def authority(value):
    need(type(value) is dict and set(value) == {'s0_execute','g1_execute','cleanup'} and all(v is False for v in value.values()))


def source_pins(pins, provider):
    need(type(pins) is dict and pins)
    for name, digest in pins.items():
        safe_name(name); need(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest))
        need(sha(provider(name)) == digest)


def junit(raw, context, expected_cases, subtests=0):
    need(len(raw) <= 2097152 and b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper())
    root = ET.fromstring(raw); suites = list(root.iter('testsuite'))
    need(len(suites) == 1)
    suite = suites[0]
    for key in ('head','run_id','attempt'): need(suite.get(key) == context[key])
    need(not any(list(root.iter(tag)) for tag in ('failure','error','skipped')))
    cases = sorted((c.get('classname'),c.get('name')) for c in root.iter('testcase'))
    need(cases == sorted(expected_cases))
    need(type(subtests) is int and subtests >= 0 and suite.get('tests') == str(len(cases)+subtests))
    need(all(suite.get(k) == '0' for k in ('errors','failures','skipped')))


def native(record, context, files, provider):
    need(set(record) == {'scope','fixture','head','token_probe_cases','normal','deadline','descendant_denied','wrong_hash_rejected','wrong_sid_rejected','run_id','attempt','binary_sha256','source_sha256'})
    check_context(record, {k:v for k,v in context.items() if k != 'tree'})
    need(record.get('scope') == 'HOSTED_FIXTURE_NOT_PHYSICAL' and record.get('fixture') is True)
    need(type(record.get('token_probe_cases')) is int and record['token_probe_cases'] == 14)
    need(record.get('wrong_hash_rejected') is True and record.get('wrong_sid_rejected') is True)
    source_pins(record['source_sha256'], provider)
    need(record['binary_sha256']['S0Launcher.dll'] == sha(files['native/S0Launcher.dll']))
    identities = set(); sid = None
    for label,budget,timeout in (('normal',5,False),('deadline',1,True),('descendant_denied',5,False)):
        fact = record[label]
        need(type(fact) is dict and set(fact) == {'pid','creation_filetime','exit_code','timed_out','budget_seconds','observed_user_sid','observed_elevated','observed_integrity','observed_admin_enabled','job_member','job_flags','active_limit'})
        for key in ('pid','creation_filetime'): need(type(fact.get(key)) is int and fact[key] > 0)
        identity = (fact['pid'],fact['creation_filetime']); need(identity not in identities); identities.add(identity)
        need(type(fact.get('exit_code')) is int and 0 <= fact['exit_code'] <= 0xffffffff)
        if not timeout: need(fact['exit_code'] == 0)
        need(fact.get('timed_out') is timeout and type(fact.get('budget_seconds')) is int and fact['budget_seconds'] == budget)
        need(fact.get('observed_elevated') is False and fact.get('observed_admin_enabled') is False and fact.get('job_member') is True)
        need(fact.get('observed_integrity') == 'S-1-16-8192')
        need(type(fact.get('job_flags')) is int and fact['job_flags'] == 8200 and type(fact.get('active_limit')) is int and fact['active_limit'] == 1)
        observed = fact.get('observed_user_sid'); need(type(observed) is str and re.fullmatch(r'S-1-5-21-(?:[0-9]+-){3}[0-9]+',observed))
        if sid is None: sid = observed
        need(sid == observed)


BOOTSTRAP_CASES = frozenset(('plan_no_write','unapproved_rejected','wrong_sha_rejected','wrong_sid_rejected','outside_parent_rejected','stage_closure','existing_target_rejected','concurrent_no_replace','canary_unchanged'))
BOOTSTRAP_SOURCES = frozenset(('installer/physical-smoke-s0/S0Launcher.cs','installer/physical-smoke-s0/S0Bootstrap.cs','installer/physical-smoke-s0/TokenObserver.cs','installer/physical-smoke-s0/S0Inputs.cs','installer/physical-smoke-s0-tests/BootstrapTests.cs','installer/physical-smoke-s0-tests/InputTests.cs','tools/verify_s0_bootstrap_ci.py'))
TOKEN_SOURCES = frozenset(('installer/physical-smoke-s0/TokenObserver.cs','installer/physical-smoke-s0-tests/TokenObserverTests.cs','installer/physical-smoke-s0-tests/TokenObserverFixture.cs'))
TOKEN_TRUE = frozenset(('pure_cases','parent_admin_rejected','standard_primary_accepted','sid_matches','wrong_sid_rejected','medium'))


def preparation_records(outer, context, package_sha, dll_sha, provider):
    expected = {k:v for k,v in context.items() if k != 'tree'}
    record = strict_json(outer['s0-results/native-bootstrap.json'])
    base_keys = BOOTSTRAP_CASES | {'scope','head','package_sha256','status','s0_execute','g1_execute','cleanup'}
    need(type(record) is dict and set(record) == base_keys | {'run_id','attempt','fixture_sha256','source_sha256'})
    check_context(record,expected)
    need(record['scope'] == 'HOSTED_BOOTSTRAP_NOT_PHYSICAL' and record['status'] == 'PASS' and record['package_sha256'] == package_sha)
    need(all(record[k] is True for k in BOOTSTRAP_CASES) and all(record[k] is False for k in ('s0_execute','g1_execute','cleanup')))
    need(type(record['source_sha256']) is dict and set(record['source_sha256']) == BOOTSTRAP_SOURCES)
    source_pins(record['source_sha256'],provider)
    raw = outer['s0-results/native-bootstrap-raw.json']; need(0 < len(raw) <= 16384)
    need(record['fixture_sha256'] == sha(raw) and json.dumps(strict_json(raw),sort_keys=True) == json.dumps({k:record[k] for k in base_keys},sort_keys=True))
    record = strict_json(outer['s0-results/native-token-observer.json'])
    base_keys = TOKEN_TRUE | {'scope','component','head','status','elevated','group_count','privilege_count','enabled_privilege_count','physical_acceptance'}
    need(type(record) is dict and set(record) == base_keys | {'run_id','attempt','binary_sha256','source_sha256'})
    check_context(record,expected)
    need(record['scope'] == 'HOSTED_FIXTURE_NOT_PHYSICAL' and record['component'] == 'TOKEN_OBSERVER' and record['status'] == 'TEST_PASS')
    need(all(record[k] is True for k in TOKEN_TRUE) and record['elevated'] is False and record['physical_acceptance'] is False)
    for key,minimum,maximum in (('group_count',1,4096),('privilege_count',0,4096),('enabled_privilege_count',0,1)):
        need(type(record[key]) is int and minimum <= record[key] <= maximum)
    need(record['enabled_privilege_count'] <= record['privilege_count'])
    need(type(record['source_sha256']) is dict and set(record['source_sha256']) == TOKEN_SOURCES)
    source_pins(record['source_sha256'],provider)
    binaries = record['binary_sha256']; need(type(binaries) is dict and set(binaries) == {'S0Launcher.dll','TokenObserverFixture.exe'})
    need(all(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) for value in binaries.values()) and binaries['S0Launcher.dll'] == dll_sha)
    raw = outer['s0-results/native-token-observer-raw.txt']; need(0 < len(raw) <= 8192)
    need(json.dumps(strict_json(raw),sort_keys=True) == json.dumps({k:record[k] for k in base_keys},sort_keys=True))


def public_probe(record, context):
    need(set(record) == {'schema','head','run_id','attempt','scope','physical_ready','s0_execute','g1_execute','status','counts','duration_ms','error','http_status','samples','detail','last_operation'})
    need(type(record['schema']) is int and record['schema'] == 1 and type(record['duration_ms']) is int and 0 <= record['duration_ms'] <= 15000)
    check_context(record,{k:v for k,v in context.items() if k != 'tree'})
    need(record.get('scope') == 'PUBLIC_HOSTED_DIAGNOSTIC_ONLY')
    need(all(record.get(k) is False for k in ('physical_ready','s0_execute','g1_execute')))
    counts = record['counts']; need(set(counts) == {'subscribe_ack','book_samples','trade_samples','samples'})
    need(type(counts['subscribe_ack']) is bool)
    for key in ('book_samples','trade_samples','samples'): need(type(counts[key]) is int and 0 <= counts[key] <= 4)
    need(counts['samples'] == counts['book_samples'] + counts['trade_samples'] == len(record['samples']))
    error = record['error']; need(error is None or error in {'INCOMPLETE','TIMEOUT','HTTP_ERROR','TLS_ERROR','TRANSPORT_ERROR','PROTOCOL_ERROR','UNEXPECTED_ERROR'})
    if record['http_status'] is not None: need(error == 'HTTP_ERROR' and type(record['http_status']) is int and 100 <= record['http_status'] <= 599)
    observed = counts['subscribe_ack'] and counts['book_samples'] and counts['trade_samples'] and error is None
    need(record['status'] == ('OBSERVED_PUBLIC_NOT_PHYSICAL' if observed else 'BLOCKED'))
    books = trades = 0
    for sample in record['samples']:
        need(set(sample) == {'topic','sha256','size'} and type(sample['size']) is int and 0 < sample['size'] <= 2097152)
        need(type(sample['sha256']) is str and re.fullmatch('[0-9a-f]{64}',sample['sha256']))
        need(sample['topic'] in {'orderbook.1.BTCUSDT','publicTrade.BTCUSDT'})
        books += sample['topic'] == 'orderbook.1.BTCUSDT'; trades += sample['topic'] == 'publicTrade.BTCUSDT'
    need(books == counts['book_samples'] and trades == counts['trade_samples'])


def journal(raw, context):
    need(raw and raw.endswith(b'\n') and len(raw) <= ENTRY)
    previous = '0'*64; records = []
    for number,line in enumerate(raw.splitlines(),1):
        row = strict_json(line)
        need(type(row) is dict and set(row) == {'seq','previous','payload','sha256'})
        need(type(row['seq']) is int and row['seq'] == number and row['previous'] == previous)
        hashed = json.dumps({k:row[k] for k in ('seq','previous','payload')},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
        need(sha(hashed) == row['sha256'])
        payload = row['payload']; check_context(payload,context)
        need(set(payload) == set(context) | {'kind','utc_ms','value'} and type(payload['utc_ms']) is int and type(payload['value']) is dict)
        previous = row['sha256']; records.append(payload)
    return records


def check(outer_raw, outer_sha, context, provider):
    """Provider returns independently reviewed exact Git object bytes; never executes Git."""
    need(set(context) == {'head','tree','run_id','attempt'})
    for key in ('head','tree'): need(re.fullmatch('[0-9a-f]{40}',context[key]))
    for key in ('run_id','attempt'): need(re.fullmatch('[1-9][0-9]{0,19}',context[key]))
    need(type(outer_sha) is str and re.fullmatch('[0-9a-f]{64}',outer_sha) and sha(outer_raw) == outer_sha)
    outer = archive_members(outer_raw)
    receipt = strict_json(outer['s0-package/package-receipt.json']); check_context(receipt,context); authority(receipt['authority'])
    need(set(receipt) == {'schema','profile','package','sha256','size','authority','head','tree','run_id','attempt','python','source'})
    need(type(receipt.get('schema')) is int and receipt['schema'] == 1 and receipt.get('profile') == 'PHYSICAL_SMOKE_S0')
    name = receipt['package']; safe_name(name); need('/' not in name)
    package_raw = outer['s0-package/'+name]
    need(sha(package_raw) == receipt['sha256'] and type(receipt.get('size')) is int and len(package_raw) == receipt['size'])
    files = archive_members(package_raw); manifest = strict_json(files['s0-package.json'])
    need(set(manifest) == {'schema','profile','authority','files','head','tree','run_id','attempt','python','source'})
    check_context(manifest,context); authority(manifest['authority'])
    need(type(manifest['schema']) is int and manifest['schema'] == 1 and manifest['profile'] == 'PHYSICAL_SMOKE_S0')
    need(re.fullmatch(r'3\.12\.[0-9]+',manifest['python']) and receipt['python'] == manifest['python'])
    need(manifest['source'] == receipt['source'] and REQUIRED_SOURCES <= set(manifest['source']))
    source_pins(manifest['source'],provider)
    need(set(files) == set(manifest['files']) | {'s0-package.json'})
    for path,pin in manifest['files'].items():
        need(type(pin) is dict and set(pin) == {'sha256','size'} and type(pin['size']) is int)
        need(pin == {'sha256':sha(files[path]),'size':len(files[path])})
        need(not path.endswith(('tls-key.pem','config.json')))
    for path,digest in manifest['source'].items():
        target = 'runtime/App/'+path if path.startswith('s0_smoke/') else path
        need(sha(files[target]) == digest)
    inv = strict_json(provider('integration/s0_inventory.json'))
    idx = strict_json(outer['s0-results/hosted-sha256.json']); check_context(idx,context)
    need(set(idx) == {'head','tree','run_id','attempt','phase','scope','g1_execute','physical_sid_acl','tests','subtests','files','sources','nodes'})
    need(idx['phase'] == 'hosted' and idx['scope'] == 'SYNTHETIC_OFFLINE_OR_HOSTED_NOT_PHYSICAL')
    need(idx.get('g1_execute') is False and idx.get('physical_sid_acl') == '0/10 NOT_RUN')
    need(idx.get('nodes') == inv['hosted_nodes'] and type(idx.get('tests')) is int and idx['tests'] == len(idx['nodes']))
    need(type(idx.get('subtests')) is int and idx['subtests'] == 0)
    source_pins(idx['sources'],provider)
    need(set(idx['files']) == {'hosted.xml','hosted.jsonl'})
    for path,digest in idx['files'].items(): need(sha(outer['s0-results/'+path]) == digest)
    rows = [strict_json(line) for line in outer['s0-results/hosted.jsonl'].splitlines()]
    need([r['node'] for r in rows] == idx['nodes'])
    for row in rows:
        check_context(row,context); need(row.get('status') == 'TEST_PASS' and row.get('g1_execute') is False and row.get('physical_sid_acl') == '0/10 NOT_RUN')
    xml = outer['s0-results/hosted.xml']
    need(len(xml) <= 2097152 and b'<!DOCTYPE' not in xml.upper() and b'<!ENTITY' not in xml.upper())
    parsed = ET.fromstring(xml)
    cases = [(c.get('classname'),c.get('name')) for c in parsed.iter('testcase')]
    need(sorted(n for _,n in cases) == sorted(n.split('::')[-1] for n in idx['nodes']))
    junit(xml,context,cases)
    native(strict_json(outer['s0-results/native-launcher.json']),context,files,provider)
    preparation_records(outer,context,receipt['sha256'],sha(files['native/S0Launcher.dll']),provider)
    public_probe(strict_json(outer['s0-results/public-probe.json']),context)
    portable = strict_json(outer['s0-results/portable.json']); check_context(portable,context)
    need(set(portable) == {'head','tree','run_id','attempt','package_sha256','status','runs','s0_execute','g1_execute','physical'} and portable['physical'] == 'NOT_RUN')
    need(portable.get('package_sha256') == receipt['sha256'] and portable.get('status') == 'PORTABLE_PLAN_AND_IMPORTS_PASS' and portable.get('s0_execute') is False and portable.get('g1_execute') is False)
    summaries = []
    for role in ('LS5','PC4'):
        prefix = 's0-results/component-fixture/'+role+'/'
        summary = strict_json(outer[prefix+'summary.json'])
        need(set(summary) == {'schema','head','run_id','role','tree','package_sha256','scope','status','result','error','g1_execute','physical_sid_acl','cleanup_authorized','deployment'})
        need(type(summary['schema']) is int and summary['schema'] == 1)
        check_context(summary,dict(head=context['head'],tree=context['tree'],role=role))
        need(summary.get('status') == 'BLOCKED_OR_PARTIAL' and summary.get('physical_sid_acl') == '0/10 NOT_RUN' and summary.get('deployment') == 'NO-GO')
        need(summary.get('g1_execute') is False and summary.get('cleanup_authorized') is False)
        index = strict_json(outer[prefix+'sha256.json'])
        need(set(index) == {'schema','head','run_id','role','package_sha256','files','g1_execute','cleanup_authorized'})
        need(type(index['schema']) is int and index['schema'] == 1)
        need(index.get('g1_execute') is False and index.get('cleanup_authorized') is False)
        check_context(index,dict(head=context['head'],run_id=summary['run_id'],role=role))
        need(index.get('package_sha256') == summary.get('package_sha256') == 'b'*64 and set(index['files']) >= {'events.jsonl','claim.json','summary.json','results.xml'})
        for path,digest in index['files'].items(): safe_name(path); need('/' not in path and sha(outer[prefix+path]) == digest)
        need(summary.get('scope') == 'S0_PUBLIC_ONLY_NOT_GRID_ACCEPTANCE')
        events = journal(outer[prefix+'events.jsonl'],dict(head=context['head'],run_id=summary['run_id'],role=role))
        need(events[0]['kind'] == 'started' and events[-1]['kind'] == 'finished')
        need(events[-1]['value'] == dict(result=summary['result'],error=summary['error']))
        result_xml = outer[prefix+'results.xml']
        need(len(result_xml) <= 2097152 and b'<!DOCTYPE' not in result_xml.upper() and b'<!ENTITY' not in result_xml.upper())
        result_suite = ET.fromstring(result_xml)
        need(result_suite.tag == 'testsuite' and result_suite.get('head') == context['head'] and result_suite.get('run_id') == summary['run_id'])
        need(all(result_suite.get(k) == v for k,v in dict(tests='1',errors='0',skipped='0',failures='1').items()))
        need(len(list(result_suite.iter('testcase'))) == 1 and len(list(result_suite.iter('failure'))) == 1)
        need(summary['result'].get('final') is True); summaries.append(summary)
    a,b = summaries
    need(a['run_id'] == b['run_id'] and all(a['result'][k] == b['result'][k] for k in ('stats','heartbeats')))
    return dict(status='OFFLINE_EVIDENCE_CHECK_PASS_NOT_APPROVAL',approval='BLOCKED',physical='0/10 NOT_RUN',g1='20/20 BLOCKED',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO',requirements_version=REQUIREMENTS_VERSION,**context)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('head','tree','run-id','attempt','outer-sha256','artifact','source-bytes'): parser.add_argument('--'+key,required=True)
    args = parser.parse_args(); root = Path(args.source_bytes)
    def provider(name):
        safe_name(name); return (root / name).read_bytes()
    try:
        path = Path(args.artifact); need(path.stat().st_size <= LIMIT)
        result = check(path.read_bytes(),args.outer_sha256,dict(head=args.head,tree=args.tree,run_id=args.run_id,attempt=args.attempt),provider)
    except (ValueError,KeyError,TypeError,OSError,zipfile.BadZipFile,ET.ParseError,RecursionError):
        print(json.dumps(dict(status='OFFLINE_EVIDENCE_CHECK_BLOCKED',approval='BLOCKED'))); return 1
    print(json.dumps(result,sort_keys=True)); return 0

if __name__ == '__main__':
    raise SystemExit(main())
