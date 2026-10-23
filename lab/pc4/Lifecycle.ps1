#Requires -Version 5.1
# Accept only the originally retained Process object, never look up or kill PID.
# Providers in offline tests are synthetic objects and a no-I/O signal callback.
function Stop-Pc4Actor($Process,[scriptblock]$Signal){
 $signalFailed=$false
 try {
  if($null -eq $Process){throw 'PROCESS_UNKNOWN'}
  if($Process.HasExited -isnot [bool]){throw 'EXIT_TYPE_UNKNOWN'}
  if(!$Process.HasExited){
   try {& $Signal|Out-Null}catch{$signalFailed=$true}
   $wait=$Process.WaitForExit(5000)
   if($wait -isnot [bool]){throw 'WAIT_TYPE_UNKNOWN'}
   if(!$wait){
    return [pscustomobject]@{status='BLOCKED_TIMEOUT';exit_code=$null;signal_failed=$signalFailed}
   }
  }
  if($Process.HasExited -isnot [bool] -or !$Process.HasExited -or $Process.ExitCode -isnot [int]){throw 'EXIT_UNCONFIRMED'}
  return [pscustomobject]@{status='EXIT_CONFIRMED';exit_code=[int]$Process.ExitCode;signal_failed=$signalFailed}
 } catch {
  return [pscustomobject]@{status='BLOCKED_UNKNOWN';exit_code=$null;signal_failed=$signalFailed}
 }
}
