"""Read-only discovery among explicitly configured CONTROL endpoints."""
import asyncio
from urllib.parse import urlsplit
import aiohttp
from .config import settings


class ControlUnavailable(RuntimeError):
    pass


def candidates():
    configured=settings.coordinator_candidates
    if not configured:return []
    if len(configured)>8:raise ValueError('at most eight CONTROL candidates are supported')
    result=[]
    for address in configured:
        parsed=urlsplit(address)
        if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/')):
            raise ValueError('CONTROL candidate must be an explicit HTTP(S) origin without credentials')
        # Validate malformed ports before making any network request.
        parsed.port
        normalized=address.rstrip('/')
        if normalized not in result:result.append(normalized)
    return result


async def _probe(address):
    # Separate session: worker credentials and caller default headers cannot
    # leak into discovery, redirects or environment proxy authentication.
    async with aiohttp.ClientSession() as session:
        async with session.get(address+'/health',allow_redirects=False,
                               timeout=aiohttp.ClientTimeout(total=3)) as reply:
            if reply.status!=200:return None
            return await reply.json()


async def active_control_url(*,probe=None):
    addresses=candidates()
    if not addresses:return settings.coordinator_url
    probe=probe or _probe
    async def read(address):
        try:
            async with asyncio.timeout(3):result=await probe(address)
            if (isinstance(result,dict) and result.get('ok') is True
                and result.get('control_leader') is True
                and type(result.get('control_epoch')) is int and result['control_epoch']>0
                and isinstance(result.get('control_owner'),str) and result['control_owner']):
                return address
        except Exception:
            pass
        return None
    active=[address for address in await asyncio.gather(*(read(a) for a in addresses)) if address]
    if len(active)!=1:raise ControlUnavailable('CONTROL discovery requires exactly one active endpoint')
    return active[0]
