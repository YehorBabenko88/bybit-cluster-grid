import asyncio
from grid.control_plane import command_result


class Conn:
    def __init__(self,belongs=True):
        self.belongs=belongs;self.calls=[]
    async def execute(self,sql,*args):
        self.calls.append((sql,args))
        return "UPDATE 1" if self.belongs else "UPDATE 0"


class Acquire:
    def __init__(self,conn):self.conn=conn
    async def __aenter__(self):return self.conn
    async def __aexit__(self,*args):return False


class Pool:
    def __init__(self,belongs=True):self.conn=Conn(belongs)
    def acquire(self):return Acquire(self.conn)


def test_command_ack_is_bound_to_node_identity():
    async def run():
        p=Pool(True)
        assert await command_result(p,"cmd",True,{"ok":1},None,node_id="node-a") is True
        sql,args=p.conn.calls[0]
        assert "node_id=$5" in sql
        assert args[-1]=="node-a"
    asyncio.run(run())


def test_wrong_node_ack_is_rejected():
    async def run():
        p=Pool(False)
        assert await command_result(p,"cmd",True,{},None,node_id="node-b") is False
    asyncio.run(run())
