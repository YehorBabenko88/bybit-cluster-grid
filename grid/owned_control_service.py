"""Fixed loopback CONTROL launcher for an already admitted protected process.

This callback is not an activation kernel. The raw external dispatcher performs
full admission before importing this module; no serialized grant is accepted.
"""
import importlib,os,re
from pathlib import Path


def main(argv=None,*,startup_admission=None):
    # No arbitrary Uvicorn options, application selector, reload or worker fork.
    if (type(argv) is not list or len(argv)!=3 or argv[:2]!=['--execute','--port']
            or type(argv[2]) is not str or not argv[2].isascii() or not argv[2].isdigit()
            or not 1<=int(argv[2])<=65535 or str(int(argv[2]))!=argv[2]):
        raise ValueError('Owned CONTROL arguments unavailable')
    admission=startup_admission;head=os.environ.get('UNIFIED_SOURCE_COMMIT','')
    if (isinstance(admission,dict) or not all(callable(getattr(admission,name,None)) for name in ('require_current','source_scope'))
            or admission.require_current() is not True or re.fullmatch('[a-f0-9]{40}',head) is None
            or os.environ.get('UNIFIED_MODULE_ID')!='grid'):
        raise ValueError('Owned CONTROL source admission unavailable')
    root=Path(__file__).resolve().parents[1]
    scoped=admission.source_scope('grid',root,head)
    if (not isinstance(scoped,Path) or scoped!=root or not scoped.is_absolute()
            or any(c in str(scoped) for c in ('*','?','[',']','\n','\r','\0'))
            or admission.require_current() is not True):
        raise ValueError('Owned CONTROL source admission unavailable')
    coordinator=importlib.import_module('grid.coordinator')
    coordinator._owned_startup_scope(admission,head,verify_git=True)
    if coordinator.settings.role!='coordinator':raise ValueError('Owned CONTROL role unavailable')
    uvicorn=importlib.import_module('uvicorn')
    coordinator.app.state.owned_source_admission=admission
    # Existing ASGI startup checks this object before any DB/coordination work.
    config=uvicorn.Config(coordinator.app,host='127.0.0.1',port=int(argv[2]),
                          access_log=False,workers=1,reload=False)
    if admission.require_current() is not True:raise ValueError('Owned CONTROL source admission unavailable')
    server=uvicorn.Server(config);server.run()
    if server.started is not True:raise ValueError('Owned CONTROL startup unavailable')
    return 0
