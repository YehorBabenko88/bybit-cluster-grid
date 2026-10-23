#Requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$RunId,
      [Parameter(Mandatory=$true)][ValidateSet('Collector','Storage')][string]$Role,
      [Parameter(Mandatory=$true)][string]$ExpectedSid,
      [Parameter(Mandatory=$true)][string]$TokenAssemblySha256)
$ErrorActionPreference='Stop'
throw 'EXECUTE_NOT_AUTHORIZED' # also block direct actor invocation before any observation
. (Join-Path $PSScriptRoot 'Common.ps1')
try {
 if([Environment]::MachineName -cne 'PC4' -or ![Environment]::Is64BitProcess){throw 'HOST_BLOCKED'}
 Assert-Pc4Sid $ExpectedSid $(if($Role -ceq 'Collector'){'1003'}else{'1004'})
 $paths=Get-Pc4Paths $RunId $Role
 Assert-Pc4Plain $paths.Root
 $assembly=Join-Path $PSScriptRoot 'TokenFacts.dll'
 if($TokenAssemblySha256 -cnotmatch '^[0-9a-f]{64}$' -or (Get-Pc4Hash $assembly) -cne $TokenAssemblySha256){throw 'ASSEMBLY_HASH_BLOCKED'}
 Add-Type -Path $assembly
 $facts=[GridPc4.TokenFacts]::Read($PID,$true)
 if(!(Test-Pc4Facts $facts $ExpectedSid)){throw 'TOKEN_UNSAFE'}
 Write-Pc4NewText (Join-Path $paths.Root 'ready.json') (@{run_id=$RunId;role=$Role;pid=$PID;start_utc=[Diagnostics.Process]::GetCurrentProcess().StartTime.ToUniversalTime().ToString('O');facts=$facts}|ConvertTo-Json -Depth 8 -Compress)
 $deadline=[DateTime]::UtcNow.AddSeconds(45)
 while(!(Test-Path -LiteralPath (Join-Path $paths.Root 'go.flag'))){
  if((Test-Path -LiteralPath (Join-Path $paths.Root 'stop.flag')) -or [DateTime]::UtcNow -gt $deadline){throw 'START_GATE_TIMEOUT'}
  Start-Sleep -Milliseconds 100
 }
 $results=New-Object Collections.Generic.List[object]
 function Record([string]$Case,[bool]$Pass,[string]$Code,$Data){
  $record=[ordered]@{schema=1;source='NATIVE_PC4_LOCAL';run_id=$RunId;role=$Role;case=$Case;outcome=$(if($Pass){'PASS'}else{'FAIL'});code=$Code;pid=$PID;facts=$Data}
  $line=($record|ConvertTo-Json -Depth 8 -Compress)+"`n";$log=Join-Path $paths.Root 'actor.jsonl'
  if($results.Count -eq 0){Write-Pc4NewText $log $line}else{Add-Pc4Text $log $line}
  $results.Add($record)
 }
 if(Test-Path -LiteralPath (Join-Path $paths.Root 'stop.flag')){throw 'COOPERATIVE_STOP'}
 Record 'token' $true 'OK' $facts
 $own=Join-Path $paths.Root 'own.txt';$content=$RunId+'|'+$Role
 $ok=$false
 try {Write-Pc4NewText $own $content;if((Get-Acl -LiteralPath $own).GetOwner([Security.Principal.SecurityIdentifier]).Value -cne $ExpectedSid){throw 'OWN_FILE_OWNER_MISMATCH'};$ok=$true}
 catch {$ok=$false}
 Record 'own_write' $ok $(if($ok){'OK'}else{'OWN_IO_FAILED'}) $null
 if(Test-Path -LiteralPath (Join-Path $paths.Root 'stop.flag')){throw 'COOPERATIVE_STOP'}
 $ok=$false
 try {$bytes=[IO.File]::ReadAllText($own,$script:Pc4Utf8);if($bytes -cne $content){throw 'CONTENT_MISMATCH'};$ok=$true}
 catch {$ok=$false}
 Record 'own_read' $ok $(if($ok){'OK'}else{'OWN_IO_FAILED'}) $null
 $peer=if($Role -ceq 'Collector'){'Storage'}else{'Collector'}
 $foreign=Join-Path (Get-Pc4Paths $RunId $peer).Root 'canary.txt'
 foreach($case in @('foreign_read_denied','foreign_write_denied')){
  if(Test-Path -LiteralPath (Join-Path $paths.Root 'stop.flag')){throw 'COOPERATIVE_STOP'}
  $s=$null;$denied=$false;$code='ACCESS_UNEXPECTEDLY_ALLOWED'
  try {
   $access=if($case -ceq 'foreign_read_denied'){[IO.FileAccess]::Read}else{[IO.FileAccess]::Write}
   $s=New-Object IO.FileStream($foreign,[IO.FileMode]::Open,$access,[IO.FileShare]::ReadWrite)
  } catch {
   $e=$_.Exception;while($e.InnerException){$e=$e.InnerException}
   if(($e.HResult -band 0xffff) -eq 5){$denied=$true;$code='ACCESS_DENIED_5'}
   else {$code='ERROR_NOT_ACCESS_DENIED'}
  } finally {if($null -ne $s){$s.Dispose()}}
  # Logger errors must not be misclassified as denial of the foreign file.
  Record $case $denied $code $null
 }
 if(@($results|Where-Object outcome -ne 'PASS').Count){exit 2}
 exit 0
} catch { [Console]::Error.WriteLine('PC4_ACTOR_BLOCKED');exit 3 }
