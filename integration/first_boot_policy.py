"""Fail-closed CI-only policy. Environment guards are not physical attestation."""
import ipaddress
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
RESERVED={5432,55432,55433}


def require_ci(env=None):
    env=os.environ if env is None else env
    required=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',RUNNER_OS='Linux',
                  GITHUB_JOB='pg18',GITHUB_REPOSITORY='YehorBabenko88/bybit-cluster-grid')
    if (sys.platform!='linux' or any(env.get(k)!=v for k,v in required.items()) or env.get('DOCKER_HOST') or env.get('DOCKER_CONTEXT') or
        not re.fullmatch('[0-9a-f]{40}',env.get('EXACT_HEAD_SHA','')) or
        any(not re.fullmatch('[1-9][0-9]*',env.get(k,'')) for k in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'))):
        raise RuntimeError('FIRST_BOOT_HOSTED_ISOLATION_REQUIRED_BEFORE_OPERATIONS')


def loopback_endpoint(url):
    parsed=urlsplit(url)
    if parsed.scheme not in ('http','https','ws','wss') or parsed.username is not None or parsed.password is not None or not parsed.hostname:
        raise ValueError('FIRST_BOOT_ENDPOINT')
    try:local=ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:local=False
    port=parsed.port
    if not local or port is None or not 1024<=port<=65535 or port in RESERVED:
        raise ValueError('FIRST_BOOT_LOOPBACK_OWNED_PORT_REQUIRED')
    return parsed.hostname,port


def install_child_guard(root):
    """Python audit guard, not a kernel sandbox or protection against native extensions."""
    root=Path(root).resolve(strict=True)
    def contained(path):
        if isinstance(path,int):return  # already-open stdout/pipe/file descriptors
        p=Path(os.fsdecode(path))
        candidate=(Path.cwd()/p if not p.is_absolute() else p).resolve()
        if candidate!=root and root not in candidate.parents:raise PermissionError('FIRST_BOOT_OUTSIDE_OWNED_FIXTURE')
    def audit(event,args):
        if event in ('socket.connect','socket.bind','socket.sendto','socket.sendmsg'):
            address=args[1]
            if not isinstance(address,tuple):raise PermissionError('FIRST_BOOT_UNIX_NETWORK_BLOCKED')
            try:local=ipaddress.ip_address(address[0]).is_loopback
            except ValueError:local=False
            if not local:raise PermissionError('FIRST_BOOT_EXTERNAL_NETWORK_BLOCKED')
        elif event=='socket.getaddrinfo':
            try:local=ipaddress.ip_address(args[0]).is_loopback
            except ValueError:local=False
            if not local:raise PermissionError('FIRST_BOOT_EXTERNAL_DNS_BLOCKED')
        elif event=='open':
            mode,flags=args[1:3]
            if isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND) or isinstance(mode,str) and any(c in mode for c in 'wax+'):
                contained(args[0])
        elif event in ('os.remove','os.rmdir','os.mkdir','os.chmod'):
            contained(args[0])
            # Refuse dir_fd resolution ambiguity; these fixtures do not need it.
            if event in ('os.remove','os.rmdir') and len(args)>1 and args[1] not in (-1,None):raise PermissionError('FIRST_BOOT_DIR_FD_BLOCKED')
        elif event in ('os.rename','os.link','os.symlink'):
            contained(args[0]);contained(args[1])
            if any(x not in (-1,None) for x in args[2:] if isinstance(x,int)):raise PermissionError('FIRST_BOOT_DIR_FD_BLOCKED')
        elif event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn'):
            raise PermissionError('FIRST_BOOT_NESTED_PROCESS_BLOCKED')
    sys.addaudithook(audit)


def child_environment(base,root,role,coordinator,feed,head):
    root=Path(root).resolve(strict=True);loopback_endpoint(coordinator);loopback_endpoint(feed)
    # Deliberately do not inherit production secrets, Python hooks, proxies or PG defaults.
    keep=('PATH','SYSTEMROOT','WINDIR','HOME','LANG','LD_LIBRARY_PATH','RUNNER_TEMP','GITHUB_ACTIONS','RUNNER_ENVIRONMENT',
          'RUNNER_OS','GITHUB_JOB','GITHUB_REPOSITORY','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT')
    env={k:base[k] for k in keep if k in base}
    env.update(PYTHONPATH=str(ROOT),PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',PYTHONUNBUFFERED='1',
        ProgramData=str(root/'data'),PROGRAMDATA=str(root/'data'),ProgramFiles=str(root/'programs'),
        GRID_DATA_PATH=str(root),GRID_FIXTURE_ROOT=str(root),GRID_VERSION=head,EXACT_HEAD_SHA=head,
        TEMP=str(root/'temp'),TMP=str(root/'temp'),TMPDIR=str(root/'temp'),ROLE=role,NODE_ROLE='CONTROL' if role=='coordinator' else 'WORKER',
        COORDINATOR_URL=coordinator,COORDINATOR_CANDIDATES='[]',BYBIT_REST_URL=feed,BYBIT_WS_URL=feed.replace('http:','ws:')+'/ws',
        BYBIT_ARCHIVE_BASE_URL=feed+'/archive',ARCHIVE_ROOT=str(root/'archive'),ML_ARTIFACT_ROOT=str(root/'ml-artifacts'),
        STRATEGY_CACHE_DIR=str(root/'strategies'),GRID_CONTROL_JOURNAL=str(root/'control-state.json'),GRID_CONTROL_SNAPSHOTS=str(root/'snapshots'),
        HEARTBEAT_SECONDS='1',REBALANCE_SECONDS='1',REPLAY_START_JITTER_SECONDS='0',RESOURCE_RESERVE_CORES='0',
        RESOURCE_CPU_LIMIT='95',RESOURCE_RAM_LIMIT='95',RESOURCE_DISK_FREE_GB='0.1',DISK_SOFT_FREE_GB='0.5',DISK_HARD_FREE_GB='0.25',DISK_EMERGENCY_FREE_GB='0.1',
        TELEGRAM_BOT_TOKEN='',TELEGRAM_ALLOWED_CHAT_IDS='',TAILSCALE_OAUTH_CLIENT_ID='',TAILSCALE_OAUTH_CLIENT_SECRET='',
        RETENTION_ENABLED='false',POSTGRES_DSN='')
    return env
