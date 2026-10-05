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

    async def dataset_page(self,job,offset=0,limit=500):
        params={"node_id":self.node_id,"lease_generation":job["lease_generation"],
                "offset":int(offset),"limit":int(limit)}
        return await self._request("GET",f"/ml/jobs/{job['id']}/dataset",params=params)

    async def dataset(self,job):
        first=await self.dataset_page(job,0,500)
        if first is None:return None
        samples=[];offset=0
        while offset<int(first.get("sample_count",0)):
            page=first if offset==0 else await self.dataset_page(job,offset,500)
            if page is None:return None
            chunk=[x["payload"] for x in page.get("samples",[])]
            if not chunk:break
            samples.extend(chunk);offset+=len(chunk)
        return {"dataset_id":first["dataset_id"],"dataset_hash":first["dataset_hash"],
                "feature_version":first.get("feature_version"),
                "sample_count":int(first.get("sample_count",0)),"samples":samples}

    async def artifact(self,job,data,sha256):
        params={"node_id":self.node_id,"lease_generation":job["lease_generation"],"sha256":sha256}
        return await self._request("POST",f"/ml/jobs/{job['id']}/artifact",params=params,data=data)

    async def finalize(self,job,artifact_id,metrics):
        return await self._request("POST",f"/ml/jobs/{job['id']}/finalize",
          json={"node_id":self.node_id,"lease_generation":job["lease_generation"],
                "artifact_id":artifact_id,"metrics":metrics})
