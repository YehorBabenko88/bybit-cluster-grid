#Requires -Version 5.1
# Mock objects only; no real processes are created, queried or stopped.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Lifecycle.ps1')
$script:cases=0;$script:signals=0
function Check([bool]$Value){if(!$Value){throw 'LIFECYCLE_ASSERT_FAILED'};$script:cases++}
function ProcessFixture([bool]$Exited,[bool]$Wait,[bool]$Fault){
 $p=[pscustomobject]@{HasExited=$Exited;ExitCode=0;Wait=$Wait;Fault=$Fault}
 $p|Add-Member ScriptMethod WaitForExit {param($ms) if($ms -ne 5000 -or $this.Fault){throw 'MOCK_FAULT'};if($this.Wait){$this.HasExited=$true};return $this.Wait}
 return $p
}
$r=Stop-Pc4Actor (ProcessFixture $true $false $false) {$script:signals++}
Check ($r.status -ceq 'EXIT_CONFIRMED' -and $script:signals -eq 0)
$r=Stop-Pc4Actor (ProcessFixture $false $true $false) {$script:signals++}
Check ($r.status -ceq 'EXIT_CONFIRMED' -and $script:signals -eq 1)
$r=Stop-Pc4Actor (ProcessFixture $false $false $false) {}
Check ($r.status -ceq 'BLOCKED_TIMEOUT')
$r=Stop-Pc4Actor (ProcessFixture $false $false $true) {}
Check ($r.status -ceq 'BLOCKED_UNKNOWN')
$r=Stop-Pc4Actor (ProcessFixture $false $false $false) {throw 'SIGNAL_FAULT'}
Check ($r.status -ceq 'BLOCKED_TIMEOUT' -and $r.signal_failed)
$r=Stop-Pc4Actor $null {}
Check ($r.status -ceq 'BLOCKED_UNKNOWN')
$p=ProcessFixture $true $false $false;$p.ExitCode=3;$r=Stop-Pc4Actor $p {}
Check ($r.status -ceq 'EXIT_CONFIRMED' -and $r.exit_code -eq 3)
$p=ProcessFixture $true $false $false;$p.HasExited='true';$r=Stop-Pc4Actor $p {}
Check ($r.status -ceq 'BLOCKED_UNKNOWN')
$p=ProcessFixture $true $false $false;$p.ExitCode='0';$r=Stop-Pc4Actor $p {}
Check ($r.status -ceq 'BLOCKED_UNKNOWN')
# PID reuse model: never query or touch a replacement object with the same PID.
$old=ProcessFixture $true $false $false;$other=ProcessFixture $false $false $false
$old|Add-Member NoteProperty Id 100;$other|Add-Member NoteProperty Id 100
$r=Stop-Pc4Actor $old {}
Check ($r.status -ceq 'EXIT_CONFIRMED' -and !$other.HasExited)
Write-Output ('LIFECYCLE_CASES='+$script:cases+'; MOCK_ONLY; PHYSICAL_NOT_RUN')
