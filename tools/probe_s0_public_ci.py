"""Optional real public-feed diagnostic, genuine hosted Windows job only.

Collection exit zero includes BLOCKED (region denial, silence, or failure). This
is neither mandatory connectivity proof nor physical S0/G1 acceptance. Import
and pure classifiers are inert; never invoke main or collect locally.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import re
import socket
import ssl
import sys
import time

ERRORS = frozenset({'INCOMPLETE', 'TIMEOUT', 'HTTP_ERROR', 'TLS_ERROR', 'TRANSPORT_ERROR', 'PROTOCOL_ERROR', 'UNEXPECTED_ERROR'})


def hosted_context(env, hostname):
    """Validate supplied metadata without enumerating or serializing environment."""
    try:
        from tools.build_s0_package import require_hosted
    except ModuleNotFoundError:
        from build_s0_package import require_hosted
    require_hosted(env, hostname)
    result = dict(head=env.get('EXACT_HEAD_SHA'), run_id=env.get('GITHUB_RUN_ID'), attempt=env.get('GITHUB_RUN_ATTEMPT'))
    if type(result['head']) is not str or re.fullmatch('[0-9a-f]{40}', result['head']) is None:
        raise ValueError('PROBE_HEAD_CONTEXT')
    for key in ('run_id', 'attempt'):
        if type(result[key]) is not str or re.fullmatch('[1-9][0-9]{0,19}', result[key]) is None:
            raise ValueError('PROBE_CI_CONTEXT')
    return result


def validate_observation(ack, book_samples, trade_samples, error=None, http_status=None):
    """Pure closed classification; success requires ACK and both validated topics."""
    if type(ack) is not bool or any(type(x) is not int or not 0 <= x <= 4 for x in (book_samples, trade_samples)) or book_samples + trade_samples > 4:
        raise ValueError('PROBE_COUNTS')
    if error is not None and (type(error) is not str or error not in ERRORS):
        raise ValueError('PROBE_ERROR_CLASS')
    if http_status is not None and (error != 'HTTP_ERROR' or type(http_status) is not int or not 100 <= http_status <= 599):
        raise ValueError('PROBE_HTTP_STATUS')
    return 'OBSERVED_PUBLIC_NOT_PHYSICAL' if ack and book_samples and trade_samples and error is None else 'BLOCKED'


async def collect(context):
    """Real I/O entry point: caller must first authenticate the genuine host."""
    # Recheck here so importing the function cannot bypass the execution gate.
    hosted_context(os.environ, '')
    if hosted_context(os.environ, socket.gethostname()) != context:
        raise ValueError('PROBE_CONTEXT_CHANGED')
    import aiohttp
    from s0_smoke.policy import TOPICS, canonical, load_json, outbound
    from s0_smoke.protocol import MarketState
    from s0_smoke.runtime import public_connection, trace
    started = time.monotonic()
    ack = False; books = 0; trades = 0; error = None; http_status = None; samples = []
    state = MarketState()
    tls = ssl.create_default_context(); tls.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        # Reserve cleanup time within the ten-second diagnostic budget.
        async with asyncio.timeout(9):
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=tls, limit=1),
                    timeout=aiohttp.ClientTimeout(total=10, connect=3), trust_env=False,
                    cookie_jar=aiohttp.DummyCookieJar(), trace_configs=[trace()]) as session:
                ws = await public_connection(session)
                try:
                    await ws.send_json(outbound('subscribe'))
                    while not (books and trades):
                        message = await ws.receive()
                        if message.type == aiohttp.WSMsgType.TEXT:
                            value = load_json(message.data)
                            if 'topic' in value:
                                if not ack or value.get('topic') not in TOPICS:
                                    raise ValueError('PROBE_TOPIC_BEFORE_ACK')
                                event = state.ingest(value, int(time.time()*1000))
                                retain = (event['kind'] == 'book' and books < 3) or (event['kind'] == 'trades' and trades < 3)
                                if not retain: continue
                                if event['kind'] == 'book': books += 1
                                else: trades += 1
                                raw = canonical(value)
                                # Hash-only public samples bound evidence even for large batches.
                                samples.append(dict(topic=value['topic'], sha256=hashlib.sha256(raw).hexdigest(), size=len(raw)))
                                if books and trades: break
                            elif value.get('op') == 'subscribe':
                                if value.get('success') is not True or value.get('req_id') != 'S0':
                                    raise ValueError('PROBE_SUBSCRIBE_REJECTED')
                                ack = True
                            elif value.get('op') not in ('ping', 'pong'):
                                raise ValueError('PROBE_PUBLIC_CONTROL')
                        elif message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            raise ConnectionError('PROBE_FEED_CLOSED')
                        elif message.type not in (aiohttp.WSMsgType.PING, aiohttp.WSMsgType.PONG):
                            raise ValueError('PROBE_FRAME_TYPE')
                finally:
                    await asyncio.wait_for(ws.close(), .5)
    except aiohttp.WSServerHandshakeError as failure:
        error = 'HTTP_ERROR'
        if type(failure.status) is int and 100 <= failure.status <= 599: http_status = failure.status
    except (aiohttp.ClientConnectorCertificateError, aiohttp.ClientSSLError, ssl.SSLError): error = 'TLS_ERROR'
    except TimeoutError: error = 'TIMEOUT'
    except (aiohttp.ClientError, OSError): error = 'TRANSPORT_ERROR'
    except ValueError: error = 'PROTOCOL_ERROR'
    except Exception: error = 'UNEXPECTED_ERROR'
    if error is None and not (ack and books and trades): error = 'INCOMPLETE'
    status = validate_observation(ack, books, trades, error, http_status)
    return dict(schema=1, **context, scope='PUBLIC_HOSTED_DIAGNOSTIC_ONLY', physical_ready=False,
        s0_execute=False, g1_execute=False, status=status,
        counts=dict(subscribe_ack=ack, book_samples=books, trade_samples=trades, samples=len(samples)),
        duration_ms=int((time.monotonic()-started)*1000), error=error, http_status=http_status, samples=samples)


def main():
    # Environment gate runs before actual hostname lookup, socket, or directory work.
    hosted_context(os.environ, '')
    context = hosted_context(os.environ, socket.gethostname())
    repository = Path(__file__).resolve().parents[1]
    if str(repository) not in sys.path: sys.path.insert(0, str(repository))
    result = asyncio.run(collect(context))
    from s0_smoke.policy import canonical
    from s0_smoke.storage import write_new
    destination = repository / 's0-results'
    destination.mkdir(exist_ok=True)
    write_new(destination, 'public-probe.json', canonical(result))
    return 0  # Collection success, explicitly including BLOCKED; never an acceptance code.


if __name__ == '__main__':
    raise SystemExit(main())
