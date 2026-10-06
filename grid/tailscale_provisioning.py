import httpx

OAUTH_TOKEN_URL="https://api.tailscale.com/api/v2/oauth/token"
KEY_URL="https://api.tailscale.com/api/v2/tailnet/-/keys"

class TailscaleProvisioningError(RuntimeError):
    pass

def _tags(value):
    xs=[x.strip() for x in str(value or "").split(",") if x.strip()]
    if not xs or any(not x.startswith("tag:") for x in xs):
        raise TailscaleProvisioningError("at least one valid tag:* is required")
    return xs

async def create_one_time_auth_key(client_id,client_secret,tags,timeout=15.0):
    """Create a non-reusable, non-ephemeral, preauthorized tagged node key.

    The OAuth client secret remains CONTROL-side. Only the resulting one-time
    auth key is allowed into a bootstrap envelope.
    """
    if not str(client_id or "").strip() or not str(client_secret or "").strip():
        raise TailscaleProvisioningError("Tailscale OAuth client is not configured")
    tag_list=_tags(tags)
    async with httpx.AsyncClient(timeout=timeout) as client:
        token_resp=await client.post(
            OAUTH_TOKEN_URL,
            data={
                "client_id":client_id,
                "client_secret":client_secret,
                "scope":"auth_keys",
                "tags":" ".join(tag_list),
            },
        )
        if token_resp.status_code>=400:
            raise TailscaleProvisioningError(
                f"Tailscale OAuth token request failed ({token_resp.status_code})"
            )
        access=str(token_resp.json().get("access_token") or "")
        if not access:
            raise TailscaleProvisioningError("Tailscale OAuth returned no access token")
        key_resp=await client.post(
            KEY_URL,
            headers={"Authorization":f"Bearer {access}"},
            json={
                "capabilities":{
                    "devices":{
                        "create":{
                            "reusable":False,
                            "ephemeral":False,
                            "preauthorized":True,
                            "tags":tag_list,
                        }
                    }
                }
            },
        )
        if key_resp.status_code>=400:
            raise TailscaleProvisioningError(
                f"Tailscale auth-key request failed ({key_resp.status_code})"
            )
        key=str(key_resp.json().get("key") or "")
        if not key:
            raise TailscaleProvisioningError("Tailscale API returned no auth key")
        return key
