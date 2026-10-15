"""Synthetic planning evidence only, not a host inventory."""
import json,sys
from pathlib import Path, PureWindowsPath
RUN='1234567890abcdef1234567890abcdef'
def fleet(n=3):
    return {'schema':1,'run_id':RUN,'nodes':[{'id':'LAB'+str(i),'role':'CONTROL' if i==0 else 'WORKER',
      'address':'100.64.0.'+str(i+1),'windows_major':10,'cpu_logical':4,'ram_bytes':8*1024**3,'disk_free_bytes':40*1024**3,
      'python_version':'3.12.10','postgres_major':16,'ssh_available':True,'tailscale_available':True,
      'runtime_stopped':True,'inventory_complete':True,'test_root':str(PureWindowsPath('C:/GridLab')/RUN/('LAB'+str(i))),
      'test_root_exists':False,'disposable_cluster_confirmed':False} for i in range(n)]}

if __name__=='__main__':
    with Path(sys.argv[1]).open('x',encoding='utf-8') as f:
        json.dump(fleet(int(sys.argv[2])),f)
