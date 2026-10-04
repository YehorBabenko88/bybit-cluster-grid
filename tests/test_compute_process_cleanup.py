import asyncio
from grid.strattester_compute_worker import _terminate_tree


class GoneProcess:
    pid=999999999
    returncode=None
    async def wait(self):
        return 0


def test_terminate_tree_tolerates_already_gone_process():
    asyncio.run(_terminate_tree(GoneProcess()))
