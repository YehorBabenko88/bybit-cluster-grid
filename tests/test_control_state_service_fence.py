import asyncio
import pytest
from grid.control_state import put_control_state


class Pool:
    def __init__(self): self.calls=[]
    async def fetchrow(self,sql,*args):
        self.calls.append((sql,args))
        return {'version':2}


def test_optional_service_fence_is_bound_to_the_cas_statement():
    pool=Pool()
    assert asyncio.run(put_control_state(pool,'key',{},'one',expected_version=1,
        service_fence={'service_key':'control-plane-leader','owner':'one','epoch':7}))==2
    sql,args=pool.calls[0]
    assert 'service_leases' in sql and 'FOR SHARE' in sql
    assert 'clock_timestamp()' in sql and 'version=$4' in sql
    assert args[4:]==('control-plane-leader','one',7)


def test_default_legacy_control_state_paths_are_unchanged():
    for version in (None,3):
        pool=Pool()
        assert asyncio.run(put_control_state(pool,'key',{'safe':True},'one',expected_version=version))==2
        sql,args=pool.calls[0]
        assert 'service_leases' not in sql
        assert len(args)==(3 if version is None else 4)


@pytest.mark.parametrize('fence',[{}, {'service_key':'arbitrary SQL','owner':'one','epoch':1},
    {'service_key':'control-plane-leader','owner':'other','epoch':1},
    {'service_key':'control-plane-leader','owner':'one','epoch':True}])
def test_invalid_fence_is_rejected_before_database(fence):
    pool=Pool()
    with pytest.raises(ValueError):
        asyncio.run(put_control_state(pool,'key',{},'one',expected_version=1,service_fence=fence))
    assert pool.calls==[]
