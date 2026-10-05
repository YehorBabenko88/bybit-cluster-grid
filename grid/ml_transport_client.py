import aiohttp
from .config import settings
from .credential_store import node_credential

class MLTransportClient:
    def __init__(self,node_id,session=None):
        self.node_id=str(node_id);self.session=session

    def headers(self):
        return {"X-Grid-Token":settings.grid_shared_token,
                "X-Node-Credential":node_credential()}

    async def _request(self,method,path,**kwargs):
        owned=self.session is None
        session=self.session or aiohttp.ClientSession()
        try:
            async with session.request(method,settings.coordinator_url+path,
                                       headers=self.headers(),timeout=30,**kwargs) as r:
                if r.status==409:return None
                r.raise_for_status()
                return await r.json()
        finally:
            if owned:await session.close()

    async def claim(self):
        x=await self._request("POST","/ml/claim",json={"node_id":self.node_id})
        return None if x is None else x.get("job")

    async def renew(self,job):
        return await self._request("POST",f"/ml/jobs/{job['id']}/renew",
          json={"node_id":self.node_id,"lease_generation":job["lease_generation"]})

    async def dataset(self,job):
        params={"node_id":self.node_id,"lease_generation":job["lease_generation"]}
        return await self._request("GET",f"/ml/jobs/{job['id']}/dataset",params=params)

    async def artifact(self,job,data,sha256):
        params={"node_id":self.node_id,"lease_generation":job["lease_generation"],"sha256":sha256}
        return await self._request("POST",f"/ml/jobs/{job['id']}/artifact",params=params,data=data)

    async def finalize(self,job,artifact_id,metrics):
        return await self._request("POST",f"/ml/jobs/{job['id']}/finalize",
          json={"node_id":self.node_id,"lease_generation":job["lease_generation"],
                "artifact_id":artifact_id,"metrics":metrics})
