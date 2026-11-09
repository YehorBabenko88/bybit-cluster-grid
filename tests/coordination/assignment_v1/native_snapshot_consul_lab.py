"""Own ACL-default-deny loopback triplet; no service/system/foreign processes."""
import hashlib,json,os,socket,subprocess,sys,time,urllib.request,urllib.error,uuid
from pathlib import Path

PINS={'win32':'41762ef5b98c8dd9b6852df6cfbceed37e7f0acc5760856be33100f1092475e1',
      'linux':'acb0a1b5b2a22a5fadb5d725f03610335e499e193eeade9df458c6c6017a77f4'}
class ConsulLab:
    def __init__(self,binary,scratch):
        self.binary=Path(binary).resolve();self.scratch=Path(scratch).resolve()
        assert hashlib.sha256(self.binary.read_bytes()).hexdigest()==PINS[sys.platform]
        self.token=str(uuid.uuid4())  # own disposable admin only, never emitted
        self.processes=[];self.logs=[];self.nodes=[]
    def __enter__(self):
        self.scratch.mkdir(parents=True,exist_ok=False)
        ports=[];reserved=[]
        try:
            for _ in range(12):
                item=socket.socket();item.bind(('127.0.0.1',0));reserved.append(item);ports.append(item.getsockname()[1])
        finally:
            for item in reserved: item.close()
        try:
            for i in range(3):
                folder=self.scratch/str(i);folder.mkdir()
                rpc,lan,wan,http=ports[i*4:i*4+4]
                value=dict(server=True,bootstrap_expect=3,datacenter='research-identity-lab',node_name='research-'+str(i),
                    data_dir=str(folder/'data'),bind_addr='127.0.0.1',advertise_addr='127.0.0.1',client_addr='127.0.0.1',
                    ports=dict(server=rpc,serf_lan=lan,serf_wan=wan,http=http,https=-1,dns=-1,grpc=-1,grpc_tls=-1),
                    retry_join=['127.0.0.1:'+str(ports[j*4+1]) for j in range(3) if j!=i],
                    disable_update_check=True,disable_remote_exec=True,enable_script_checks=False,
                    leave_on_terminate=False,skip_leave_on_interrupt=True,log_level='warn',performance=dict(raft_multiplier=1),
                    connect=dict(enabled=False),raft_logstore=dict(backend='boltdb'),
                    acl=dict(enabled=True,default_policy='deny',enable_token_persistence=True,
                        tokens=dict(initial_management=self.token,agent=self.token)))
                path=folder/'config.json';path.write_text(json.dumps(value),encoding='utf-8')
                log=(folder/'consul.log').open('ab');self.logs.append(log)
                env=os.environ.copy();env['CHECKPOINT_DISABLE']='1'
                p=subprocess.Popen([str(self.binary),'agent','-config-file',str(path)],stdout=log,stderr=subprocess.STDOUT,
                    env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                self.processes.append(p);self.nodes.append('http://127.0.0.1:'+str(http))
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                assert all(p.poll() is None for p in self.processes)
                try:
                    for node in self.nodes:
                        status,raw=self.request(node,'GET','/v1/operator/raft/configuration?consistent')
                        assert status==200
                        voters=json.loads(raw)['Servers']
                        assert len(voters)==3 and all(v['Voter'] for v in voters) and sum(v['Leader'] for v in voters)==1
                    print(json.dumps(dict(scope='OWNED_LOOPBACK_LAB_STARTED',voters=3,
                        processes=[p.pid for p in self.processes],endpoints=self.nodes,
                        binary_sha256=PINS[sys.platform],acl_default='deny')),flush=True)
                    return self
                except (OSError,ValueError,KeyError,AssertionError): time.sleep(.2)
            raise RuntimeError('OWNED_ACL_CONSUL_START_TIMEOUT')
        except BaseException:
            self.__exit__(None,None,None);raise
    def request(self,endpoint,method,path,data=None,*,authenticated=True):
        headers={'Content-Type':'application/json'}
        if authenticated: headers['X-Consul-Token']=self.token
        request=urllib.request.Request(endpoint+path,data=data,method=method,headers=headers)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request,timeout=2) as response: return response.status,response.read(1048576)
        except urllib.error.HTTPError as exc: return exc.code,exc.read(1048576)
    def __exit__(self,*args):
        for process in self.processes:
            if process.poll() is None: process.kill()
        for process in self.processes: process.wait(timeout=10)
        for log in self.logs: log.close()
        assert all(process.poll() is not None for process in self.processes)
        print(json.dumps(dict(scope='OWNED_LOOPBACK_LAB_RETIRED',
            processes=[dict(pid=p.pid,returncode=p.returncode) for p in self.processes],
            all_owned_processes_waited=True,foreign_process_operations=0,
            session_retirement='OWNED_SERVERS_STOPPED_TEMPORARY_DIRECTORY_CLEANUP_FOLLOWS')),flush=True)
