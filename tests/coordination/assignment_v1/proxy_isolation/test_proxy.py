"""Actual owned Core + inherited own proxy trap + Consul consistent READ only."""
import json,os,subprocess,sys,tempfile,threading,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from native_snapshot_consul_lab import ConsulLab

ROOT=Path(__file__).absolute().parents[4]

class ProxyTrap(BaseHTTPRequestHandler):
    def do_GET(self):
        # Never record path, headers, ACL token or body. Counter only.
        with self.server.counter_lock:self.server.requests+=1
        self.send_response(403);self.send_header('Content-Length','0');self.end_headers();self.close_connection=True
    def log_message(self,*args):pass

class ProxyIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='a2-proxy-read-only-')
        binary=os.environ.get('A2_NATIVE_CONSUL_BINARY','C:/Users/LS-5/Documents/Codex/2026-11-06/codex-agent-8-independent-security-ci/work/consul-bin/extracted/consul.exe')
        cls.lab=ConsulLab(binary,Path(cls.temp.name)/'consul')
        try:cls.lab.__enter__()
        except BaseException:cls.temp.cleanup();raise
    @classmethod
    def tearDownClass(cls):cls.lab.__exit__(None,None,None);cls.temp.cleanup()
    def run_child(self,mode):
        server=ThreadingHTTPServer(('127.0.0.1',0),ProxyTrap);server.daemon_threads=True
        server.requests=0;server.counter_lock=threading.Lock();ready=threading.Event()
        def serve():ready.set();server.serve_forever(poll_interval=.05)
        thread=threading.Thread(target=serve,daemon=True);thread.start();self.assertTrue(ready.wait(2))
        environment=os.environ.copy()
        for key in tuple(environment):
            if key.upper() in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY'):environment.pop(key,None)
        proxy='http://127.0.0.1:'+str(server.server_port)
        environment.update(HTTP_PROXY=proxy,HTTPS_PROXY=proxy,ALL_PROXY=proxy,NO_PROXY='',A2_OWN_PROXY_TEST_ACL=self.lab.token)
        try:
            result=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).with_name('proxy_probe_child.py')),
                str(ROOT),json.dumps(self.lab.nodes),mode],env=environment,capture_output=True,timeout=15,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(result.returncode,0,result.stderr.decode());self.assertLessEqual(len(result.stdout)+len(result.stderr),4096)
            value=json.loads(result.stdout)
            print(json.dumps(dict(scope='ACTUAL_OWN_PROXY_TRAP_AND_CONSUL_READ_ONLY',proxy_ready=True,
                mode=mode,trap_requests=server.requests,child_pid_not_identity=True,result=value)),flush=True)
            return value,server.requests
        finally:
            server.shutdown();server.server_close();thread.join(2);self.assertFalse(thread.is_alive())
    def test_actual_owned_client_ignores_captured_proxy_and_reads_real_three_voters(self):
        value,count=self.run_child('OWNED')
        self.assertTrue(value['actual_three_voters']);self.assertEqual(count,0)
        self.assertIs(value['owned'],True);self.assertIs(value['trust_env'],False)
        self.assertIs(value['follow_redirects'],False);self.assertIs(value['closed_by_authority'],True)
    def test_injected_client_remains_unowned_and_not_closed_by_authority(self):
        value,count=self.run_child('INJECTED')
        self.assertIs(value['owned'],False);self.assertIs(value['trust_env'],True)
        self.assertIs(value['closed_by_authority'],False);self.assertEqual(count,0)
        self.assertTrue(value['no_request_injected_check'])

if __name__=='__main__':unittest.main()
