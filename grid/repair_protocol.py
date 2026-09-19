from .update_protocol import desired_release

async def stable_repair_request(pool,node_id,files,current_version=None):
    rel=await desired_release(pool,"stable")
    if not rel: raise RuntimeError("no enabled stable release available for repair")
    files=sorted(set(str(x) for x in files))
    if not files:return None
    return {
      "version":rel["version"],"package_url":rel["package_url"],"sha256":rel["sha256"],
      "repair_files":files,"repair_only":True,"previous_version":current_version,
    }
