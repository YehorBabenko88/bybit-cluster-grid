"""Exact raw Assignment substrate source qualification, no native grant claim."""
import argparse,hashlib,importlib.util,io,json,os,platform,subprocess,sys,unittest
from pathlib import Path
SUPPORT_HEAD='be5cb942436f82f374375eabb255768bb139797f'
GUARD_SHA='ebca27436b977265ec09a99f07f93764cb7e19080d7dad0ecb06db79cc1de38c'
REAL_CASES=['PUBLIC_ASSIGNMENT_DEFAULT_NATIVE_ABSENCE_DENIED','ACTUAL_CHECKED_NATIVE_RECEIPT_RAW_PROBE_COMMIT','ACTUAL_STALE_LEADER_NATIVE409_NO_EFFECT','ACTUAL_STALE_GENERATION_NATIVE409_NO_EFFECT','ACTUAL_SUPERSESSION_FIRST_REJECTS_PUBLICATION_SAME_KEY','ACTUAL_PUBLICATION_FIRST_RECEIPT_RETAINED_AFTER_SUPERSESSION','ACTUAL_SIMULTANEOUS_RESTART_DURABLE_NATIVE_RECEIPT_INDEX','ACTUAL_ONE_OF_THREE_NO_QUORUM_NO_CACHE_SUCCESS']
UNITS={
 'test_assignment_contract.AssignmentContractTests.test_default_missing_actual_native_provider_never_touches_consul',
 'test_assignment_contract.AssignmentContractTests.test_deep_or_noncanonical_native_record_is_rejected',
 'test_assignment_contract.AssignmentContractTests.test_distinct_storage_records_do_not_alias_issuance_lifecycle_policy_accounting',
 'test_assignment_contract.AssignmentContractTests.test_native_plan_overflow_is_rejected_before_transport',
 'test_assignment_contract.AssignmentContractTests.test_new_layout_preserves_stable_partition_key_and_rejects_unsafe_original',
 'test_assignment_contract.AssignmentContractTests.test_none_boolean_shape_is_not_a_native_provider',
 'test_runtime_policy.RuntimePolicyDataTests.test_runtime_fullmatch_bounds_namespace_and_operation_semantics',
 'test_runtime_policy.RuntimePolicyDataTests.test_schema_control_and13_terminal_newline_negatives',
 'test_runtime_policy.RuntimePolicyDataTests.test_schema_positive_u63_limit_and_no_implicit_policy_write'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--expected-head',required=True);p.add_argument('--support-source',required=True,type=Path);p.add_argument('--binary',required=True,type=Path);p.add_argument('--scratch',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 if not sys.flags.isolated or not sys.dont_write_bytecode or sys.pycache_prefix is not None:raise RuntimeError('ISOLATED_NO_BYTECODE_REQUIRED')
 root=Path(__file__).absolute().parents[3];support=a.support_source.absolute();output=a.output.absolute();scratch=a.scratch.absolute();output.mkdir(parents=True,exist_ok=False)
 helper=support/'tests/control_mux/source_runner.py';raw=helper.read_bytes();assert hashlib.sha256(raw).hexdigest()==GUARD_SHA
 spec=importlib.util.spec_from_file_location('a2_pinned_source_guard',helper);guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
 exclusions=tuple(path for path in (support,Path(sys.prefix).absolute()) if path.is_relative_to(root))
 if output.is_relative_to(root):
  if output!=root/'.assignment-evidence':raise AssertionError('EVIDENCE_PATH')
  exclusions=(*exclusions,output)
 before=guard.source_receipt(root,a.expected_head,excluded=exclusions);support_before=guard.source_receipt(support,SUPPORT_HEAD)
 controls=subprocess.run([sys.executable,'-I','-B',str(support/'tests/control_mux/verify_source_binding.py'),'--scratch',str(output/'guard-controls'),'--output',str(output/'guard-controls.json')],cwd=support,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
 (output/'guard-controls.log').write_bytes(controls.stdout);assert controls.returncode==0,controls.stdout.decode(errors='replace')[-4000:]
 source_controls=json.loads((output/'guard-controls.json').read_bytes());assert source_controls['result']=='PASS' and len(source_controls['cases'])==8
 sys.path.insert(0,str(root));executed=[]
 class Result(unittest.TextTestResult):
  def startTest(self,test):executed.append(test.id());super().startTest(test)
 stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.discover(str(root/'tests/coordination/assignment_v1')))
 (output/'units.log').write_bytes(stream.getvalue().encode());assert result.wasSuccessful() and not result.skipped and len(executed)==9 and set(executed)==UNITS,stream.getvalue()
 command=[sys.executable,'-I','-B',str(root/'tests/coordination/assignment_v1/real_native_binding.py'),'--binary',str(a.binary.absolute()),'--lab-source',str(support/'tests/control_mux/consul_lab.py'),'--scratch',str(scratch),'--output',str(output/'real-native.json')]
 real_run=subprocess.run(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240);(output/'real-native.log').write_bytes(real_run.stdout);assert real_run.returncode==0,real_run.stdout.decode(errors='replace')[-4000:]
 real=json.loads((output/'real-native.json').read_bytes());assert real['events']==REAL_CASES and real['result']=='PASS' and real['owned_processes_stopped'] is True
 assert before==guard.source_receipt(root,a.expected_head,excluded=exclusions) and support_before==guard.source_receipt(support,SUPPORT_HEAD)
 report=dict(schema='agent2.assignment-native-substrate.source-bound.v1',head=a.expected_head,primary=before,support=support_before,python=platform.python_version(),platform=platform.platform(),executed_units=executed,executed_real_cases=real['events'],source_guard_cases=source_controls['cases'],skips=[],qualification='RAW_NATIVE_CONSUL_SUBSTRATE_AND_POLICY_DATA_ONLY_NOT_ISSUED_ASSIGNMENT_OR_NATIVE_SECURITY',public_execute_reconcile='CLOSED_PENDING_EXACT_DOMAIN_AND_ACTUAL_ROOT_NATIVE_BINDING',native_identity=False,issued_assignment=False,production='NO_GO')
 (output/'source-bound.json').write_bytes((json.dumps(report,indent=2)+chr(10)).encode());print(json.dumps(dict(result='PASS',units=9,real_raw_probe_groups=8,guards=8,primary_raw_files=len(before['raw_files']),support_raw_files=len(support_before['raw_files']),production='NO_GO')))
if __name__=='__main__':main()
