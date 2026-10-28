import copy
import unittest
from tools.s0_native_receipt import validate_native

HEAD='a'*40
SID='S-1-5-21-1-2-3-1001'

def receipt():
    value=dict(scope='HOSTED_FIXTURE_NOT_PHYSICAL',fixture=True,head=HEAD,wrong_hash_rejected=True,wrong_sid_rejected=True)
    for index,(label,budget,timeout,code) in enumerate((('normal',5,False,0),('deadline',1,True,1),('descendant_denied',5,False,0)),1):
        value[label]=dict(pid=index,creation_filetime=100+index,exit_code=code,timed_out=timeout,budget_seconds=budget,observed_user_sid=SID,observed_elevated=False,observed_integrity='S-1-16-8192',observed_admin_enabled=False,job_member=True,job_flags=8200,active_limit=1)
    return value

class NativeReceiptTests(unittest.TestCase):
    def test_accepts_closed_hosted_facts_and_pid_reuse_with_new_creation(self):
        value=receipt();self.assertIs(validate_native(value,HEAD,SID),value)
        value['deadline']['pid']=value['normal']['pid']
        self.assertIs(validate_native(value,HEAD),value)

    def test_rejects_root_mutations(self):
        for key,bad in [('fixture',1),('head','b'*40),('scope','PHYSICAL'),('wrong_hash_rejected',1),('wrong_sid_rejected',False),('extra',0)]:
            value=receipt();value[key]=bad
            with self.assertRaises(ValueError):validate_native(value,HEAD)
        value=receipt();del value['fixture']
        with self.assertRaises(ValueError):validate_native(value,HEAD)
        with self.assertRaises(ValueError):validate_native(receipt(),'A'*40)
        with self.assertRaises(ValueError):validate_native(receipt(),HEAD,'S-1-5-21-1-2-3-1002')

    def test_rejects_typed_numeric_boolean_range_and_protocol_changes(self):
        integer_keys=('pid','creation_filetime','exit_code','budget_seconds','job_flags','active_limit')
        cases=[(key,bad) for key in integer_keys for bad in (True,1.0,-1)]
        cases += [('pid',0),('pid',2**32),('creation_filetime',0),('creation_filetime',2**63),('exit_code',2**32),('exit_code',1),('budget_seconds',6),('job_flags',0),('active_limit',2),('timed_out',0),('timed_out',True),('observed_elevated',0),('observed_elevated',True),('observed_admin_enabled',True),('observed_admin_enabled',0),('job_member',1),('job_member',False),('observed_integrity','S-1-16-12288'),('observed_user_sid','S-1-5-21-01-2-3-1001'),('observed_user_sid','S-1-5-21-1-2-3-4294967296'),('extra',0)]
        for key,bad in cases:
            value=receipt();value['normal'][key]=bad
            with self.subTest(key=key,bad=bad):
                with self.assertRaises(ValueError):validate_native(value,HEAD)
        for label,key,bad in [('deadline','exit_code',0),('deadline','timed_out',False),('deadline','budget_seconds',5),('descendant_denied','exit_code',1),('descendant_denied','observed_user_sid','S-1-5-21-1-2-3-1002')]:
            value=receipt();value[label][key]=bad
            with self.assertRaises(ValueError):validate_native(value,HEAD)
        value=receipt();del value['normal']['pid']
        with self.assertRaises(ValueError):validate_native(value,HEAD)
        value=receipt();value['deadline'].update(pid=1,creation_filetime=101)
        with self.assertRaises(ValueError):validate_native(value,HEAD)

if __name__=='__main__':unittest.main()
