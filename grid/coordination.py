"""Optional Consul Raft authority; never a replacement for resource-side fencing."""
import asyncio
import base64
from dataclasses import dataclass, field
import json
import math
import re
import ssl
import time
from urllib.parse import quote, urlsplit
import uuid

import httpx


class CoordinationUnavailable(RuntimeError):
    pass


class CoordinationLost(CoordinationUnavailable):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


@dataclass(frozen=True)
class ConsulConfig:
    endpoints: tuple[str, ...]
    namespace: str
    acl_token: str = field(default='', repr=False)
    ca_bundle: str | None = None
    client_certificate: str | None = None
    client_key: str | None = field(default=None, repr=False)
    isolated_lab: bool = False
    ttl_seconds: int = 15
    request_timeout: float = 2.0

    def __post_init__(self):
        if (type(self.endpoints) is not tuple or not 1 <= len(self.endpoints) <= 5
                or len(set(self.endpoints)) != len(self.endpoints)):
            raise ValueError('one to five distinct Consul endpoints required')
        if (type(self.namespace) is not str or len(self.namespace) > 200
                or not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', self.namespace)):
            raise ValueError('explicit coordination namespace required')
        if type(self.isolated_lab) is not bool:
            raise ValueError('isolated_lab must be explicit boolean')
        for endpoint in self.endpoints:
            p = urlsplit(endpoint)
            if (p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password
                    or p.path not in ('', '/') or p.query or p.fragment):
                raise ValueError('ordinary HTTP(S) Consul endpoint required')
            if not self.isolated_lab and p.scheme != 'https':
                raise ValueError('production Consul requires HTTPS')
        if not self.isolated_lab and not all((self.acl_token, self.ca_bundle, self.client_certificate, self.client_key)):
            raise ValueError('production Consul requires ACL token, trusted CA and mutual TLS certificate/key')
        if type(self.ttl_seconds) is not int or not 10 <= self.ttl_seconds <= 3600:
            raise ValueError('Consul TTL must be between 10 and 3600 seconds')
        if (type(self.request_timeout) not in (int, float) or not math.isfinite(self.request_timeout)
                or not 0 < self.request_timeout < self.ttl_seconds / 3):
            raise ValueError('request deadline must be positive and below a third of session TTL')


@dataclass(frozen=True)
class ConsulLease:
    owner: str
    session_id: str
    token: int


class ConsulSessionAuthority:
    def __init__(self, config: ConsulConfig, *, client=None, clock=time.monotonic):
        self.config = config
        self.key = config.namespace + '/leader'
        self.clock = clock
        self._sessions = {}
        self._deadlines = {}
        self._owns_client = client is None
        if client is not None and not config.isolated_lab:
            raise ValueError('injected HTTP transports are restricted to isolated lab configuration')
        if client is None:
            context = ssl.create_default_context()
            if config.ca_bundle:
                context.load_verify_locations(cafile=config.ca_bundle)
            if config.client_certificate:
                context.load_cert_chain(config.client_certificate, config.client_key)
            client = httpx.AsyncClient(verify=context, follow_redirects=False)
        self.client = client

    async def close(self):
        if self._owns_client:
            await self.client.aclose()

    async def _request(self, method, path, *, missing_ok=False, **kwargs):
        headers = {'X-Consul-Token': self.config.acl_token} if self.config.acl_token else {}
        async def attempt():
            budget = self.config.request_timeout / len(self.config.endpoints)
            for endpoint in self.config.endpoints:
                try:
                    response = await asyncio.wait_for(
                        self.client.request(method, endpoint.rstrip('/') + path,
                            headers=headers, timeout=budget, **kwargs), timeout=budget)
                except (httpx.HTTPError, asyncio.TimeoutError):
                    continue
                if response.status_code >= 500:
                    continue
                if response.status_code == 404 and missing_ok:
                    return None
                if response.status_code == 409:
                    raise CoordinationLost('Consul fencing transaction rejected')
                if response.status_code != 200 or len(response.content) > 65536:
                    raise CoordinationUnavailable('Consul request denied or invalid response')
                try:
                    return response.json()
                except (ValueError, TypeError):
                    raise CoordinationUnavailable('Consul returned invalid JSON') from None
            raise CoordinationUnavailable('Consul quorum endpoint unavailable')
        try:
            return await asyncio.wait_for(attempt(), timeout=self.config.request_timeout)
        except asyncio.TimeoutError:
            raise CoordinationUnavailable('Consul request deadline exceeded') from None

    async def _read_lock(self):
        rows = await self._request('GET', '/v1/kv/' + quote(self.key, safe='/'),
                                   params={'consistent': ''}, missing_ok=True)
        if rows is None:
            return None
        if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
            raise CoordinationUnavailable('Consul lock record invalid')
        return rows[0]

    def _matches(self, row, lease):
        try:
            return (row is not None and row.get('Key') == self.key
                    and row['Session'] == lease.session_id
                    and type(row['ModifyIndex']) is int and row['ModifyIndex'] == lease.token
                    and json.loads(base64.b64decode(row['Value'], validate=True)) ==
                        {'owner': lease.owner, 'session_id': lease.session_id, 'namespace': self.config.namespace})
        except (ValueError, TypeError, KeyError):
            return False

    async def acquire(self, owner):
        if type(owner) is not str or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', owner):
            raise ValueError('stable owner identifier required')
        started = self.clock()
        created = await self._request('PUT', '/v1/session/create', json={
            'Name': 'grid-control-' + owner, 'TTL': str(self.config.ttl_seconds) + 's',
            'Behavior': 'release', 'LockDelay': '0s', 'NodeChecks': []})
        try:
            session = str(uuid.UUID(created['ID']))
        except (ValueError, TypeError, KeyError):
            raise CoordinationUnavailable('Consul session identity invalid') from None
        try:
            value = canonical({'owner': owner, 'session_id': session, 'namespace': self.config.namespace})
            won = await self._request('PUT', '/v1/kv/' + quote(self.key, safe='/'),
                                      params={'acquire': session}, content=value)
            if won is not True:
                await self._request('PUT', '/v1/session/destroy/' + session)
                return None
            row = await self._read_lock()
            token = row.get('ModifyIndex') if row else None
            if type(token) is not int or not 0 < token < (1 << 63):
                raise CoordinationLost('Consul fencing token invalid')
            lease = ConsulLease(owner, session, token)
            if not self._matches(row, lease) or self.clock() >= started + self.config.ttl_seconds - 1:
                raise CoordinationLost('Consul acquisition no longer current')
            self._sessions[session] = lease
            self._deadlines[session] = started + self.config.ttl_seconds - 1
            return lease
        except BaseException:
            try:
                await self._request('PUT', '/v1/session/destroy/' + session)
            except CoordinationUnavailable:
                pass
            raise

    async def validate(self, lease):
        if (type(lease) is not ConsulLease
                or self._sessions.get(lease.session_id) != lease):
            return False
        deadline = self._deadlines.get(lease.session_id, 0)
        if self.clock() >= deadline:
            return False
        try:
            row = await self._read_lock()
            return (self.clock() < deadline
                    and self._deadlines.get(lease.session_id, 0) >= deadline
                    and self._sessions.get(lease.session_id) == lease
                    and self._matches(row, lease))
        except CoordinationUnavailable:
            return False

    async def renew(self, lease):
        if self._sessions.get(getattr(lease, 'session_id', None)) != lease:
            return False
        started = self.clock()
        if started >= self._deadlines[lease.session_id]:
            return False
        try:
            result = await self._request('PUT', '/v1/session/renew/' + lease.session_id)
            if (type(result) is not list or len(result) != 1
                    or result[0].get('ID') != lease.session_id or not await self.validate(lease)):
                self._deadlines[lease.session_id] = 0
                return False
            self._deadlines[lease.session_id] = started + self.config.ttl_seconds - 1
            return True
        except CoordinationUnavailable:
            self._deadlines[lease.session_id] = 0
            return False

    async def release(self, lease):
        if self._sessions.get(getattr(lease, 'session_id', None)) != lease:
            return
        self._deadlines[lease.session_id] = 0
        try:
            # Destroying our own session releases the persistent KV lock. Never
            # delete the key: its Raft ModifyIndex remains the resource fence.
            await self._request('PUT', '/v1/session/destroy/' + lease.session_id)
        finally:
            self._sessions.pop(lease.session_id, None)

    def _state_key(self, name):
        if type(name) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', name):
            raise ValueError('bounded control record name required')
        return self.config.namespace + '/state/' + name

    async def write_control(self, lease, name, payload):
        if not await self.validate(lease):
            raise CoordinationLost('current quorum-backed lease required')
        value = canonical({'owner': lease.owner, 'token': lease.token, 'session_id': lease.session_id, 'payload': payload})
        if len(value) > 32768:
            raise ValueError('control record exceeds byte budget')
        operations = [
            {'KV': {'Verb': 'check-session', 'Key': self.key, 'Session': lease.session_id}},
            {'KV': {'Verb': 'check-index', 'Key': self.key, 'Index': lease.token}},
            {'KV': {'Verb': 'set', 'Key': self._state_key(name), 'Value': base64.b64encode(value).decode()}},
        ]
        result = await self._request('PUT', '/v1/txn', json=operations)
        if type(result) is not dict or result.get('Errors'):
            raise CoordinationLost('Consul fencing transaction rejected')

    async def read_control(self, name):
        rows = await self._request('GET', '/v1/kv/' + quote(self._state_key(name), safe='/'),
                                   params={'consistent': ''}, missing_ok=True)
        if rows is None:
            return None
        try:
            return json.loads(base64.b64decode(rows[0]['Value'], validate=True))
        except (KeyError, TypeError, ValueError, IndexError):
            raise CoordinationUnavailable('control record invalid') from None


def floating_leader_guard(leader):
    """Return the existing PG epoch only while both independent fences are current."""
    async def guard():
        authority = leader.coordination
        lease = leader.coordination_lease
        epoch = leader.epoch
        if (authority is None or lease is None or not leader.is_leader or leader.requires_fencing
                or type(epoch) is not int or epoch <= 0 or lease.owner != leader.node_id):
            raise CoordinationLost('DCS-backed Grid leadership required')
        if not await authority.validate(lease):
            raise CoordinationLost('Grid DCS session is no longer current')
        try:
            current = await asyncio.wait_for(leader.pool.fetchval("""SELECT EXISTS(SELECT 1 FROM service_leases
                WHERE service_key='control-plane-leader' AND owner=$1
                AND (metadata->>'epoch')::bigint=$2 AND lease_until>now())""", leader.node_id, epoch),
                timeout=authority.config.request_timeout)
        except Exception:
            raise CoordinationLost('Grid resource fence unavailable within deadline') from None
        if (current is not True or not await authority.validate(lease) or not leader.is_leader
                or leader.epoch != epoch or leader.coordination_lease != lease):
            raise CoordinationLost('Grid leadership changed while checking fence')
        return {'owner': leader.node_id, 'epoch': epoch}
    return guard


async def coordinator_authority(settings, *, external_fence_verifier=None):
    """Explicit startup factory. No environment flag certifies an OS watchdog."""
    mode = getattr(settings, 'grid_coordination_mode', 'legacy')
    required = getattr(settings, 'grid_ha_required', False)
    if mode not in ('legacy', 'consul'):
        raise ValueError('unknown coordination mode')
    if required and mode != 'consul':
        raise ValueError('configured HA requires Consul; PostgreSQL-only fallback is forbidden')
    if mode == 'legacy':
        return None
    isolated = getattr(settings, 'grid_coordination_isolated_lab', False)
    if required or not isolated:
        if external_fence_verifier is None or not callable(external_fence_verifier):
            raise ValueError('independent external writer fence/watchdog is not qualified')
        if await external_fence_verifier() is not True:
            raise ValueError('independent external writer fence/watchdog is not qualified')
    if not getattr(settings, 'grid_control_node_id', ''):
        raise ValueError('stable GRID_CONTROL_NODE_ID required for Consul control')
    token = getattr(settings, 'consul_acl_token', '')
    if hasattr(token, 'get_secret_value'):
        token = token.get_secret_value()
    config = ConsulConfig(endpoints=tuple(settings.consul_endpoints), namespace=settings.consul_namespace,
        acl_token=token, ca_bundle=settings.consul_ca_bundle,
        client_certificate=settings.consul_client_certificate, client_key=settings.consul_client_key,
        ttl_seconds=settings.consul_ttl_seconds, request_timeout=settings.consul_request_timeout,
        isolated_lab=isolated)
    return ConsulSessionAuthority(config)
