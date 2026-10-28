import struct
import unittest
from dataclasses import replace
from s0_smoke import windows as w


def sid(rid=1000):
    return b'\x01\x01' + b'\x00'*5 + b'\x05' + struct.pack('<I', rid)


def acl(kind=0, flags=0, mask=0x40, who=None):
    body = struct.pack('<I', mask) + (who or sid())
    ace = struct.pack('<BBH', kind, flags, len(body)+4) + body
    return struct.pack('<BBHHH', 2, 0, len(ace)+8, 1, 0) + ace


class SecurityTests(unittest.TestCase):
    def test_security_descriptor_regions_are_bounded_before_decoding(self):
        owner=sid(); dacl=acl(); raw=bytearray(20)+owner+dacl
        raw[0]=1; struct.pack_into('<H',raw,2,4)
        self.assertEqual(w.validate_sd_regions(bytes(raw),20,20+len(owner)),(owner,dacl,4))
        for owner_offset,dacl_offset in ((-1,32),(19,32),(len(raw),32),(20,31),(20,len(raw)),(20,20)):
            with self.assertRaises(w.WindowsBlocked): w.validate_sd_regions(bytes(raw),owner_offset,dacl_offset)
        for bad in (bytes(19),bytes(65537),bytes([2])+bytes(raw)[1:],bytes(raw[:2])+b'\x00\x00'+bytes(raw[4:]),
                    bytes(raw[:-1])):
            with self.assertRaises(w.WindowsBlocked): w.validate_sd_regions(bad,20,32)

    def test_file_specific_write_rights_block_untrusted_while_ancestor_create_is_allowed(self):
        trusted={w.SYSTEM,w.ADMINS,'S-1-5-2000'}
        for mask in (2,4,0x10,0x100):
            w.validate_acl(acl(mask=mask),trusted)
            with self.assertRaises(w.WindowsBlocked): w.validate_acl(acl(mask=mask),trusted,file=True)
        w.validate_acl(acl(mask=2,flags=8),trusted,file=True)
    def test_tcp_listener_decoder_both_families_and_network_port(self):
        for family,stride,state_offset,port_offset in ((2,24,0,8),(23,56,48,20)):
            row=bytearray(stride); struct.pack_into('<I',row,state_offset,2)
            row[port_offset:port_offset+4]=b'\x1f\x90\xff\xff'
            raw=struct.pack('<I',1)+row
            self.assertFalse(w.decode_tcp_listeners(raw,family,8080))
            self.assertTrue(w.decode_tcp_listeners(raw,family,8081))
            self.assertTrue(w.decode_tcp_listeners(struct.pack('<I',0),family,8080))

    def test_tcp_listener_decoder_rejects_ambiguity(self):
        for raw in (b'',struct.pack('<I',4097),struct.pack('<I',1),struct.pack('<I',0)+b'x',
                    struct.pack('<I',1)+bytes(24)):
            with self.assertRaises(w.WindowsBlocked): w.decode_tcp_listeners(raw,2,8080)
        for family,port in ((True,8080),(2,True),(2,0),(2,65536),(99,8080)):
            with self.assertRaises(w.WindowsBlocked): w.decode_tcp_listeners(struct.pack('<I',0),family,port)

    def test_port_available_checks_both_families_without_socket_calls(self):
        class Tables:
            def __init__(self): self.calls=[]
            def tcp_table(self,family):
                self.calls.append(family)
                row=bytearray(56); struct.pack_into('<I',row,48,2); row[20:22]=b'\x1f\x90'
                return struct.pack('<I',0) if family==2 else struct.pack('<I',1)+row
        api=Tables()
        self.assertFalse(w.port_available(8080,api=api)); self.assertEqual(api.calls,[2,23])
    def test_privilege_decoder_enabled_flags_and_luid_layout(self):
        data=struct.pack('<I',3)+struct.pack('<IiI',7,-1,2)+struct.pack('<IiI',8,0,0)+struct.pack('<IiI',9,0,3)
        calls=[]
        def lookup(low,high):
            calls.append((low,high)); return 'SeChangeNotifyPrivilege' if low==7 else 'SeBackupPrivilege'
        self.assertEqual(w.decode_privileges(data,lookup),('SeChangeNotifyPrivilege','SeBackupPrivilege'))
        self.assertEqual(calls,[(7,-1),(9,0)])

    def test_privilege_decoder_rejects_invalid_counts_layout_attributes_and_lookup(self):
        for data in (b'',struct.pack('<I',4097),struct.pack('<I',1),struct.pack('<I',0)+b'x',
                     struct.pack('<IIiI',1,1,0,8),struct.pack('<IIiI',1,1,0,6)):
            with self.assertRaises(w.WindowsBlocked): w.decode_privileges(data,lambda *args:'SeBackupPrivilege')
        for value in ('',None,True,'X'*257):
            with self.assertRaises(w.WindowsBlocked):
                w.decode_privileges(struct.pack('<IIiI',1,1,0,2),lambda *args:value)

    def test_operator_requires_explicit_medium_nonadmin_privilege_metadata(self):
        identity=w.Identity('S-1-5-1000',1,2,False,'S-1-16-8192',False,'C:\\a',('SeChangeNotifyPrivilege',))
        w.require_operator(identity)
        for changes in ({'elevated':True},{'admin_enabled':True},{'integrity':'S-1-16-12288'},
                        {'enabled_privileges':None},{'enabled_privileges':('SeBackupPrivilege',)},
                        {'elevated':0},{'admin_enabled':0},{'enabled_privileges':'SeChangeNotifyPrivilege'},
                        {'enabled_privileges':True}):
            with self.assertRaises(w.WindowsBlocked): w.require_operator(replace(identity,**changes))
        with self.assertRaises(w.WindowsBlocked):
            w.require_operator(w.Identity('S-1-5-1000',1,2,False,'S-1-16-8192',False,'C:\\a'))
        with self.assertRaises(w.WindowsBlocked): w.require_operator(object())
    def test_sid_decoder(self):
        self.assertEqual(w.decode_sid(sid()), 'S-1-5-1000')

    def test_untrusted_delete_child_is_blocked(self):
        with self.assertRaises(w.WindowsBlocked):
            w.validate_acl(acl(), {'S-1-5-18'})

    def test_inherit_only_does_not_apply(self):
        w.validate_acl(acl(flags=8), {'S-1-5-18'})

    def test_unknown_ace_is_blocked_even_inherit_only(self):
        with self.assertRaises(w.WindowsBlocked):
            w.validate_acl(acl(kind=9, flags=8), {'S-1-5-18'})

    def test_deny_does_not_make_later_allow_safe(self):
        with self.assertRaises(w.WindowsBlocked):
            w.validate_acl(acl(), {'S-1-5-18'})

    def test_truncated_acl_is_blocked(self):
        with self.assertRaises(w.WindowsBlocked):
            w.validate_acl(acl()[:-1], {'S-1-5-18'})

    def test_unknown_flags_and_reserved_acl_fields_are_blocked(self):
        for data in (acl(flags=0x20), acl()[:1]+b'\x01'+acl()[2:], acl()[:6]+b'\x01\x00'+acl()[8:]):
            with self.assertRaises(w.WindowsBlocked): w.validate_acl(data, {'S-1-5-1000'})

    def test_ambiguous_paths_and_files_outside_root_are_blocked(self):
        for path in ('C:\\safe\\..\\a','C:\\safe\\.\\a','C:\\safe\\NUL','C:\\safe\\a:stream',
                     '\\\\server\\share\\a','C:\\safe\\a.','C:\\safe\\a '):
            with self.assertRaises(w.WindowsBlocked): w.Custody(path,'S-1-5-1000',api=Fake())
        for path in ('C:\\safe-other\\a','C:\\a','D:\\safe\\a'):
            with self.assertRaises(w.WindowsBlocked): w.Custody('C:\\safe','S-1-5-1000',[path],api=Fake())

    def test_admin_deny_only_is_not_enabled(self):
        self.assertFalse(w.admin_group_enabled([('S-1-5-32-544', 0x14)]))
        self.assertTrue(w.admin_group_enabled([('S-1-5-32-544', 4)]))

    def test_root_requires_exact_full_control_entries(self):
        trusted = {w.SYSTEM, w.ADMINS, 'S-1-5-1000'}
        w.validate_acl(w.root_acl('S-1-5-1000'), trusted, root=True)
        with self.assertRaises(w.WindowsBlocked):
            w.validate_acl(acl(mask=w.FULL), trusted, root=True)

    def test_sid_roundtrip_and_malformed_sid(self):
        self.assertEqual(w.decode_sid(w.encode_sid('S-1-5-32-544')), w.ADMINS)
        for value in (b'', sid() + b'\x00', b'\x02' + sid()[1:]):
            with self.assertRaises(w.WindowsBlocked): w.decode_sid(value)


class Fake:
    def __init__(self):
        self.closed = []; self.opens = []; self.changed = False
    def open(self, path, directory):
        self.opens.append((path, directory)); return path
    def local_volume(self,drive): return True
    def inspect(self, handle):
        return {'identity': (1, handle, self.changed), 'directory': handle != 'C:\\safe\\a',
                'reparse': False, 'links': 1, 'owner': 'S-1-5-1000',
                'acl': acl(mask=0, who=sid()), 'protected': True}
    def close(self, handle): self.closed.append(handle)


class CustodyTests(unittest.TestCase):
    def test_nonlocal_or_unknown_volume_blocks_before_open(self):
        for result in (False,None,1):
            api=Fake(); api.local_volume=lambda drive:result
            with self.assertRaises(w.WindowsBlocked):
                with w.Custody('C:\\safe','S-1-5-1000',api=api): pass
            self.assertEqual(api.opens,[])
    def test_exclusive_file_checks_security_identity_and_releases(self):
        api=Fake(); original=api.inspect; state={}; opens=[]
        api.open_exclusive=lambda path:opens.append(path) or path
        def inspect(h):
            info=original(h); info.update(directory=False,acl=w.root_acl('S-1-5-1000')); info.update(state); return info
        api.inspect=inspect
        with w.ExclusiveFile('C:\\safe\\ownclaim.json','S-1-5-1000',api=api) as lease:
            lease.guard(); state['identity']=(99,99,99)
            with self.assertRaises(w.WindowsBlocked): lease.guard()
        self.assertEqual(opens,['C:\\safe\\ownclaim.json'])
        self.assertEqual(api.closed,opens)

    def test_exclusive_file_sharing_failure_has_no_fallback(self):
        api=Fake(); attempts=[]
        def open_exclusive(path):
            attempts.append(path); raise w.WindowsBlocked()
        api.open_exclusive=open_exclusive
        api.open_mutable=lambda path:self.fail('must not fall back to shared opening')
        with self.assertRaises(w.WindowsBlocked):
            with w.ExclusiveFile('C:\\safe\\ownclaim.json','S-1-5-1000',api=api): pass
        self.assertEqual(attempts,['C:\\safe\\ownclaim.json'])
    def test_fresh_file_checks_before_write_and_flushes_under_parent_pin(self):
        api=Fake(); original=api.inspect; events=[]
        def inspect(h):
            info=original(h); info['acl']=w.root_acl('S-1-5-1000')
            if h=='C:\\safe\\key': info['directory']=False
            events.append('inspect'); return info
        api.inspect=inspect
        def create(path,sddl):
            self.assertFalse(api.closed); self.assertIn('D:P',sddl); events.append('create'); return path
        api.create_file=create
        api.write=lambda handle,data:events.append(('write',data))
        api.flush=lambda handle:events.append('flush')
        w.create_fresh_file('C:\\safe\\key','S-1-5-1000',b'secret',api=api)
        self.assertLess(events.index('create'),events.index(('write',b'secret')))
        self.assertEqual(events[events.index('create')+1],'inspect')
        self.assertLess(events.index(('write',b'secret')),events.index('flush'))
        self.assertIn('C:\\safe\\key',api.closed)

    def test_fresh_file_rejects_bad_identity_before_write(self):
        api=Fake(); original=api.inspect; writes=[]
        def inspect(h):
            info=original(h); info['acl']=w.root_acl('S-1-5-1000')
            if h=='C:\\safe\\key': info.update(directory=False,links=2)
            return info
        api.inspect=inspect; api.create_file=lambda *args:'C:\\safe\\key'
        api.write=lambda *args:writes.append(args)
        with self.assertRaises(w.WindowsBlocked): w.create_fresh_file('C:\\safe\\key','S-1-5-1000',b'x',api=api)
        self.assertEqual(writes,[])

    def test_fresh_file_rejects_large_or_nonbytes_payload_before_open(self):
        for data in (b'x'*(1024*1024+1),'secret',True):
            api=Fake()
            with self.assertRaises(w.WindowsBlocked): w.create_fresh_file('C:\\safe\\key','S-1-5-1000',data,api=api)
            self.assertEqual(api.opens,[])

    def test_mutable_lease_checks_identity_and_security(self):
        api=Fake(); original=api.inspect; state={}
        api.open_mutable=lambda path:path
        def inspect(h):
            info=original(h); info.update(directory=False,acl=w.root_acl('S-1-5-1000')); info.update(state); return info
        api.inspect=inspect
        with w.MutableFile('C:\\safe\\stop.json','S-1-5-1000',api=api) as lease:
            self.assertEqual(lease.handle,'C:\\safe\\stop.json'); lease.guard()
            state['links']=2
            with self.assertRaises(w.WindowsBlocked): lease.guard()
        self.assertEqual(api.closed,['C:\\safe\\stop.json'])

    def test_guard_revalidates_security_and_attributes(self):
        for drift in ({'acl':acl()}, {'owner':'S-1-5-999'}, {'reparse':True},
                      {'directory':False}, {'protected':False}):
            api=Fake(); original=api.inspect; state={}
            def inspect(h):
                info=original(h)
                if h=='C:\\safe':
                    info['acl']=w.root_acl('S-1-5-1000'); info.update(state)
                return info
            api.inspect=inspect
            with w.Custody('C:\\safe','S-1-5-1000',api=api) as custody:
                state.update(drift)
                with self.assertRaises(w.WindowsBlocked): custody.guard()

    def test_guard_detects_changed_identity_and_closes(self):
        api = Fake()
        # Strict root ACL is deliberately checked independently of ancestors.
        api.inspect_original = api.inspect
        def inspect(h):
            result = api.inspect_original(h)
            if h == 'C:\\safe': result['acl'] = w.root_acl('S-1-5-1000')
            return result
        api.inspect = inspect
        with w.Custody('C:\\safe', 'S-1-5-1000', ['C:\\safe\\a'], api=api) as custody:
            api.changed = True
            with self.assertRaises(w.WindowsBlocked): custody.guard()
        self.assertEqual(len(api.closed), len(api.opens))

    def test_reparse_is_rejected(self):
        api = Fake()
        original = api.inspect
        api.inspect = lambda h: dict(original(h), reparse=True)
        with self.assertRaises(w.WindowsBlocked):
            with w.Custody('C:\\safe', 'S-1-5-1000', api=api): pass
        self.assertEqual(len(api.closed), 1)

    def test_file_hardlinks_are_blocked(self):
        api = Fake(); original = api.inspect
        def inspect(h):
            result = original(h)
            if h == 'C:\\safe': result['acl'] = w.root_acl('S-1-5-1000')
            if h == 'C:\\safe\\a': result['links'] = 2
            return result
        api.inspect = inspect
        with self.assertRaises(w.WindowsBlocked):
            with w.Custody('C:\\safe', 'S-1-5-1000', ['C:\\safe\\a'], api=api): pass
        self.assertEqual(len(api.closed), len(api.opens))

    def test_fresh_creation_pins_parent_and_never_adopts_existing(self):
        api = Fake(); created = []
        def create(path, sddl):
            created.append((path,sddl))
            self.assertFalse(api.closed)
        api.create_directory = create
        w.create_fresh_root('C:\\safe\\new', 'S-1-5-1000', api=api)
        self.assertEqual(created[0][0], 'C:\\safe\\new')
        self.assertIn('D:P', created[0][1])
        self.assertNotIn(('C:\\safe\\new',True), api.opens)
        self.assertEqual(len(api.closed), len(api.opens))

    def test_access_denied_is_not_retried_or_fallback(self):
        api = Fake()
        api.open = lambda *args: (_ for _ in ()).throw(w.WindowsBlocked())
        with self.assertRaises(w.WindowsBlocked):
            with w.Custody('C:\\safe', 'S-1-5-1000', api=api): pass

def test_native_diagnostics_are_json_serializable_and_preserve_acl():
    import json
    raw=acl()
    info=dict(owner='S-1-5-18',acl=raw,identity=(1,2,3),directory=True,reparse=False,links=1,protected=True)
    result=w.diagnostic_observation('C:\\',info)
    assert json.loads(json.dumps(result))['acl_hex']==raw.hex()
    assert info['acl']==raw
