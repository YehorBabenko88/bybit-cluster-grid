"""Real loopback HTTP/WebSocket fixture, synthetic bytes only. No exchange calls."""
import asyncio
import contextlib
import time
from aiohttp import web

SYMBOLS=('BTCUSDT','ETHUSDT')


def instrument_payload():
    return dict(retCode=0,result=dict(nextPageCursor='',list=[dict(symbol=s,status='Trading',contractType='LinearPerpetual',
        settleCoin='USDT',priceFilter=dict(tickSize='0.1')) for s in SYMBOLS]))


def trade_payload(symbol,now,sequence,minute_start=None):
    # Synthetic minute, emitted only into the disposable test database.
    start=(now//60000)*60000-60000 if minute_start is None else minute_start
    first=dict(T=start+1000,p='100.0',v='2.0',S='Buy',i=f'SYNTHETIC-{symbol}-{start}-buy')
    second=dict(T=start+2000,p='100.1',v='1.0',S='Sell',i=f'SYNTHETIC-{symbol}-{start}-sell')
    return dict(topic='publicTrade.'+symbol,ts=now,data=[first,dict(first),second])


class SyntheticFeed:
    def __init__(self):self.connections=0;self.frames=0;self.runner=None;self.url=None;self.pause=False;self.reject_ack=False;self.bad_rest=False;self.minute_start=(int(time.time()*1000)//60000)*60000
    async def advance(self):
        self.pause=True
        target=max(self.minute_start+60000,(int(time.time()*1000)//60000+1)*60000)
        await asyncio.sleep(max(0,(target+2500-int(time.time()*1000))/1000))
        self.minute_start=target
        self.pause=False
    async def instruments(self,request):
        return web.json_response(dict(retCode=10001,result={}) if self.bad_rest else instrument_payload())
    async def websocket(self,request):
        ws=web.WebSocketResponse();await ws.prepare(request);self.connections+=1
        try:
            msg=await asyncio.wait_for(ws.receive_json(),5);topics=msg.get('args',[])
            await ws.send_json(dict(op='subscribe',success=not self.reject_ack,args=topics))
            sequence=1
            while not ws.closed:
                if not self.pause:
                    now=int(time.time()*1000)
                    for topic in topics:
                        symbol=topic.split('.')[-1]
                        if symbol not in SYMBOLS:raise ValueError('unknown synthetic symbol')
                        if topic.startswith('publicTrade.'):payload=trade_payload(symbol,now,sequence,self.minute_start)
                        elif topic.startswith('orderbook.'):
                            payload=dict(topic=topic,type='snapshot' if sequence==1 else 'delta',ts=now,
                                         data=dict(s=symbol,b=[['99.9','5']],a=[['100.1','5']],u=sequence,seq=sequence))
                        elif topic.startswith('tickers.'):
                            payload=dict(topic=topic,type='snapshot',ts=now,data=dict(symbol=symbol,openInterest='1000',openInterestValue='100000',
                                fundingRate='0.0001',markPrice='100',indexPrice='100',lastPrice='100',bid1Price='99.9',ask1Price='100.1',volume24h='10000',turnover24h='1000000'))
                        else:raise ValueError('unknown synthetic topic')
                        await ws.send_json(payload);self.frames+=1
                    sequence+=1
                # Functional first boot, not a throughput benchmark: bounded input.
                await asyncio.sleep(1.0)
        except (asyncio.CancelledError,ConnectionError,TimeoutError):pass
        finally:self.connections-=1;await ws.close()
        return ws
    async def start(self):
        from .first_boot_policy import require_ci,loopback_endpoint
        require_ci()  # before a single socket bind; never physical/local execution
        app=web.Application();app.router.add_get('/v5/market/instruments-info',self.instruments);app.router.add_get('/ws',self.websocket)
        app.router.add_get('/archive/{tail:.*}',lambda request:web.Response(text='<html>SYNTHETIC_EMPTY_ARCHIVE</html>',content_type='text/html'))
        self.runner=web.AppRunner(app,shutdown_timeout=3);await self.runner.setup();site=web.TCPSite(self.runner,'127.0.0.1',0);await site.start()
        port=site._server.sockets[0].getsockname()[1];self.url=f'http://127.0.0.1:{port}';loopback_endpoint(self.url);return self.url
    async def close(self):
        if self.runner:await self.runner.cleanup()
