#Requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Python,[switch]$Native)
$ErrorActionPreference='Stop'
# Explicit test launcher only. Handles never cross the child process boundary:
# native verification AND callback run in that one Python fixture process.
$driver=Join-Path $PSScriptRoot 'ownership_session_driver.py'
if(!(Test-Path -LiteralPath $Python -PathType Leaf) -or !(Test-Path -LiteralPath $driver -PathType Leaf)){throw 'OWNERSHIP_FIXTURE_DEPENDENCY_MISSING'}
$backend=if($Native){'native'}else{'model'}
$lines=@(& $Python -B $driver --backend $backend)
if($LASTEXITCODE -ne 0){throw 'OWNERSHIP_FIXTURE_DRIVER_BLOCKED'}
$r=($lines -join "`n")|ConvertFrom-Json
if($r.schema -ne 1 -or $r.status -cne 'BLOCKED' -or $r.assurance -cne 'SYNTHETIC_ONLY' -or
   $r.synthetic_result -cne 'PASS' -or $r.cases -ne 10 -or $r.backend -cne $backend -or
   $r.execution_authorized -ne $false -or $r.physical_ready -ne $false){throw 'OWNERSHIP_FIXTURE_REPORT_INVALID'}
$r|ConvertTo-Json -Compress
