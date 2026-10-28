import base64
import copy
import hashlib
import struct
import unittest
from tools.s0_ssh_transfer_plan import build_transfer_plan

def record():
    wire=struct.pack('>I',11)+b'ssh-ed25519'+struct.pack('>I',32)+bytes(range(32))
    a=r'C:\Users\source\AppData\Local';b=r'C:\Users\ls4\AppData\Local'
    src=a+r'\GridS0Input-11111111-1111-4111-8111-111111111111';dst=b+r'\GridS0Input-22222222-2222-4222-8222-222222222222'
    return dict(head='a'*40,run_id='33333333-3333-4333-8333-333333333333',attempt='1',package_sha256='b'*64,payload_sha256='c'*64,payload_size=1024,
        ssh_path=r'C:\Windows\System32\OpenSSH\ssh.exe',ssh_sha256='d'*64,scp_path=r'C:\Windows\System32\OpenSSH\scp.exe',scp_sha256='e'*64,
        host='100.100.1.2',username='ls4',host_key_blob=base64.b64encode(wire).decode(),host_key_fingerprint='SHA256:'+base64.b64encode(hashlib.sha256(wire).digest()).decode().rstrip('='),
        source_known_folder=a,source_root=src,source_path=src+r'\pc4-role.zip',recipient_known_folder=b,recipient_root=dst,recipient_path=dst+r'\incoming.zip',
        recipient_identity=dict(root_id='1234abcd:0000000000000011',file_id='1234abcd:0000000000000012'),private_key_path=r'C:\Users\source\.ssh\id_ed25519',approved_private_key_path=r'C:\Users\source\.ssh\id_ed25519')

class SshTransferPlanTests(unittest.TestCase):
    def test_plan_is_inert_and_pinned(self):
        data=record();out=build_transfer_plan(data)
        self.assertEqual(out['recipient_identity'],data['recipient_identity']);self.assertEqual(out['run_id'],data['run_id'])
        self.assertEqual(out['status'],'BLOCKED');self.assertIsNone(out['argv']);self.assertTrue(out['plan_only'])
        self.assertTrue(all(x is False for x in out['permissions'].values()))
        argv=out['proposed_argv'];self.assertEqual(argv[0],data['scp_path']);self.assertIn('-q',argv)
        self.assertNotIn('-p',argv);self.assertNotIn('-r',argv);self.assertNotIn('-O',argv)
        self.assertIn('StrictHostKeyChecking=yes',argv);self.assertIn('BatchMode=yes',argv)
        self.assertEqual(argv[-2],data['source_path']);self.assertTrue(argv[-1].startswith('ls4@100.100.1.2:C:/'))
        self.assertEqual(out['known_hosts_path'],data['source_root']+r'\known_hosts')
        self.assertNotIn('PRIVATE KEY',repr(out));self.assertNotIn('Sid',repr(out))
        self.assertEqual(out['gates'],dict(owner_authorization='BLOCKED',receiver_lease='BLOCKED',actual_g0='BLOCKED'))
        data=record();data['host']='fd7a:115c:a1e0::1'
        self.assertIn('ls4@[fd7a:115c:a1e0::1]:',build_transfer_plan(data)['proposed_argv'][-1])

    def test_rejects_unapproved_or_injectable_inputs(self):
        changes=[('host','pc4'),('host','8.8.8.8'),('host','127.0.0.1'),('host','169.254.1.2'),('host','100.100.1.2 -oProxyCommand=x'),('username','admin'),('username','ls4;cmd'),('source_path',r'C:\shared\pc4-role.zip'),('recipient_path',r'C:\shared\incoming.zip'),('private_key_path',r'C:\Users\source\.ssh\unknown'),('private_key_path','KEYBYTES'),('host_key_fingerprint','SHA256:short'),('host_key_blob','AAAA'),('payload_size',True),('payload_size',6291457),('source_root',record()['source_root']+';cmd'),('ssh_path',r'C:\Tools\ssh.exe'),('scp_sha256','unknown'),('sid','S-1-5-21-secret')]
        for key,value in changes:
            data=record();data[key]=value
            with self.assertRaises(ValueError):build_transfer_plan(data)
        data=record();data['host_key_blob']=base64.b64encode(base64.b64decode(data['host_key_blob'])+b'x').decode()
        with self.assertRaises(ValueError):build_transfer_plan(data)
        data=record();data['recipient_identity']={}
        with self.assertRaises(ValueError):build_transfer_plan(data)
        data=record();data['host_key_fingerprint']='SHA256:'+'A'*43
        with self.assertRaises(ValueError):build_transfer_plan(data)
        data=record();del data['host_key_fingerprint']
        with self.assertRaises(ValueError):build_transfer_plan(data)
        for key in ('source_known_folder','recipient_known_folder','private_key_path','source_path','recipient_path'):
            data=record();data[key]+='$(whoami)'
            with self.assertRaises(ValueError):build_transfer_plan(data)
        data=record();data['recipient_root']=data['recipient_root'].replace('GridS0Input-','GridS0Package-')
        with self.assertRaises(ValueError):build_transfer_plan(data)

        for run in ('123','33333333-3333-3333-8333-333333333333','33333333-3333-4333-7333-333333333333','{33333333-3333-4333-8333-333333333333}'):
            data=record();data['run_id']=run
            with self.assertRaises(ValueError):build_transfer_plan(data)
        identities=[dict(volume=1,file_id='f'*32),dict(root_id='1234abcd:'+'f'*32,file_id='1234abcd:'+'e'*32),dict(root_id='1234abcd:0000000000000011',file_id='5678abcd:0000000000000012'),dict(root_id='00000000:0000000000000011',file_id='00000000:0000000000000012'),dict(root_id='1234abcd:0000000000000000',file_id='1234abcd:0000000000000012'),dict(root_id='1234abcd:0000000000000011',file_id='1234abcd:0000000000000011'),dict(root_id='1234ABCD:0000000000000011',file_id='1234ABCD:0000000000000012')]
        for identity in identities:
            data=record();data['recipient_identity']=identity
            with self.assertRaises(ValueError):build_transfer_plan(data)
