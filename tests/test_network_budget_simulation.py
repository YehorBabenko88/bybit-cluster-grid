"""Virtual ten-minute run, never a physical/live-market acceptance result."""
import importlib
from unittest.mock import patch

def test_six_nodes_ten_symbols_virtual_fault_and_recovery_matrix():
 assert importlib.util.find_spec('grid.network_budget_simulation') is not None,'synthetic network simulator missing'
 from grid.network_budget_simulation import simulate
 # These guard Python-level effects during the model run, not OS isolation.
 with patch('socket.socket',side_effect=AssertionError('no real sockets')),patch('socket.getaddrinfo',side_effect=AssertionError('no real DNS')),patch('subprocess.Popen',side_effect=AssertionError('no processes')),patch('builtins.open',side_effect=AssertionError('no files')):
  report=simulate()
 assert report['qualification']=='SYNTHETIC_MODEL_ONLY_NOT_RUNTIME_ACCEPTANCE'
 assert report['virtual_duration_ms']==600000 and report['real_network_calls']==0
 assert report['nodes']==['LS5','PC1','PC2','PC3','PC4','LS7'] and len(report['symbols'])==10
 assert report['max_pending']<=128 and report['max_http']<=4 and report['max_bulk']<=2 and report['max_ws']<=3
 assert report['reserved_bytes']['research']<=1048576*600
 assert report['byte_basis']=='RESERVED_CHARGED_SYNTHETIC_BYTES_NOT_OBSERVED_TRANSFER'
 assert report['actual_transfer_bound']=='NOT_PROVEN'
 assert 'NATIVE_MONOTONIC_IO_AND_AUTHENTICATED_DURABLE_METER_NOT_IMPLEMENTED' in report['open_p1']
 assert report['read_lifecycle']=='MODELED_500MS_SINGLE_OUTSTANDING_PER_CONNECTION'
 assert 0<report['max_outstanding_count']<=7 and 0<report['max_outstanding_bytes']<=7*65536
 assert all(report['history_symbols_by_node'][node]==report['symbols'] for node in report['nodes'])
 assert report['phases']['degraded']['research']==0 and report['phases']['degraded']['high']>0
 assert report['phases']['ls5_down']['research']==0 and report['phases']['ls5_down']['high']<=65536*6
 assert report['phases']['bybit_down']['bybit_http_opens']==0
 assert report['phases']['bybit_down']['live']==0
 assert report['phases']['bybit_down']['ws_opens']>0 and report['ws_attempts']<=200
 assert report['restart_preserved_credit'] is True
 assert report['windows_configuration_changes']==[]
