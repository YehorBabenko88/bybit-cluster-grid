"""Owned child only: inherited proxy config, actual Consul READ or no-request injection check."""
import asyncio,json,os,sys
sys.path.insert(0,sys.argv[1])
import httpx
from grid.coordination import ConsulConfig,ConsulSessionAuthority,CoordinationUnavailable

async def main():
    endpoints=tuple(json.loads(sys.argv[2]));mode=sys.argv[3]
    config=ConsulConfig(endpoints,'unified/proxy-isolation-read-only',isolated_lab=True,
        acl_token=os.environ['A2_OWN_PROXY_TEST_ACL'],request_timeout=2)
    injected=httpx.AsyncClient(trust_env=True,follow_redirects=False) if mode=='INJECTED' else None
    authority=ConsulSessionAuthority(config,client=injected)
    client=authority.client
    result=dict(mode=mode,owned=authority._owns_client,trust_env=client.trust_env,follow_redirects=client.follow_redirects)
    # Ambient changes AFTER construction cannot sanitize captured proxy mounts.
    # Only this dedicated child environment changes, never the parent/user env.
    for key in tuple(os.environ):
        if key.upper() in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY'):os.environ.pop(key,None)
    try:
        if mode=='OWNED':
            try:
                response=await authority._request('GET','/v1/operator/raft/configuration',params={'consistent':''})
                servers=response['Servers']
                result['actual_three_voters']=len(servers)==3 and all(row['Voter'] for row in servers) and sum(bool(row['Leader']) for row in servers)==1
            except CoordinationUnavailable as exc:
                result.update(actual_three_voters=False,error_type=type(exc).__name__)
        else:result['no_request_injected_check']=True
    finally:
        await authority.close()
        result['closed_by_authority']=client.is_closed
        if injected is not None:await injected.aclose()
    print(json.dumps(result,sort_keys=True))

asyncio.run(main())
