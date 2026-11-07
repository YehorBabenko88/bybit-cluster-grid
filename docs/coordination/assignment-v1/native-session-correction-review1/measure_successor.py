"""Additive successor candidate serialization only; no Consul requests."""
import base64,hashlib,json,pathlib,subprocess,sys,types
from jsonschema import Draft202012Validator
OUT=pathlib.Path(__file__).resolve().parent
OLD=OUT.parent/'RESEARCH-LAB-ADMISSION-REVIEW2'
grid=OUT.parents[1]/'work/grid-assignment-native-20261107'
raw=subprocess.check_output(['git','--no-replace-objects','-C',str(grid),'show','40e9c8dc274a2746018bc1aa08d103cd0187cecc:grid/authority_runtime_v1.py'])
assert hashlib.sha256(raw).hexdigest()=='cfb32db73f1859d9d78b03d886372cc08584c81abd64930b5409a91edc417b64'
m=types.ModuleType('successor_measure');sys.modules[m.__name__]=m;exec(compile(raw,'<pinned-runtime>','exec'),m.__dict__)
schema_raw=(OUT/'lease-lock.schema.json').read_bytes()
assert hashlib.sha256(schema_raw).hexdigest()=='9bdb1084004fcc6cfb76fa0f1bce0013b6a26a9b288cbb71c82db621feb4f4d0'
schema=json.loads(schema_raw);v=Draft202012Validator(schema);v.check_schema(schema)
old_report_raw=(OLD/'measurement.json').read_bytes()
assert hashlib.sha256(old_report_raw).hexdigest()=='75c08be72231acc2346f401e1765c23cd75810a23b644dd40e88dae71d60f390'
report={'scope':'CANDIDATE_SERIALIZATION_ONLY_NOT_NATIVE_RUNTIME_OR_ISSUER','previous_measurement_sha256':hashlib.sha256(old_report_raw).hexdigest(),'successor_lease_schema_sha256':hashlib.sha256(schema_raw).hexdigest(),'actual_consul_requests':0,'sample_native_sessions':'UNCHANGED_HISTORICAL_CANDIDATES_NOT_REAL_ISSUANCE','plans':{}}
for name,previous in json.loads(old_report_raw)['plans'].items():
    prior=(OLD/(name+'.native-plan.json')).read_bytes();assert prior.endswith(b'\n') and hashlib.sha256(prior[:-1]).hexdigest()==previous['encoded_sha256']
    plan=json.loads(prior);changes=0
    for op in plan:
        kv=op['KV']
        if 'Value' not in kv:continue
        value=json.loads(base64.b64decode(kv['Value'],validate=True))
        if value.get('schema')=='unified.authority.research-lab-lease.v1-review2':
            value['schema']=schema['properties']['schema']['const'];v.validate(value)
            kv['Value']=base64.b64encode(m.canonical(value)).decode('ascii');changes+=1
    measured=m.measure_native_plan(plan)
    report['plans'][name]={'operations':measured.operations,'encoded_bytes':measured.encoded_bytes,'encoded_sha256':measured.encoded_sha256,'lease_record_changes':changes,'operation_headroom':64-measured.operations,'bytes_headroom':32768-measured.encoded_bytes}
    encoded=json.dumps(plan,separators=(',',':'),ensure_ascii=True).encode('ascii')
    assert len(encoded)==measured.encoded_bytes and hashlib.sha256(encoded).hexdigest()==measured.encoded_sha256
    (OUT/(name+'.successor.native-plan.json')).write_bytes(encoded+b'\n')
(OUT/'successor-measurement.json').write_bytes(json.dumps(report,indent=2).encode()+b'\n')
print(json.dumps(report,indent=2))