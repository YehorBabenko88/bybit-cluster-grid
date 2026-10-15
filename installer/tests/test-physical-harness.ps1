#Requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference='Stop'
$root=Join-Path ([IO.Path]::GetTempPath()) ('physical-plan-fixture-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($root)
$planner=Join-Path $PSScriptRoot '../physical-deployment-harness.ps1'
$fixture=Join-Path $PSScriptRoot 'physical_harness_fixture.py'
$count=0
foreach($n in @(1,2,5)){
 $file=Join-Path $root ($n.ToString()+'.json')
 & $Python -B $fixture $file $n
 if($LASTEXITCODE){throw 'Fixture failed'}
 $before=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
 $argsPlan=@{EvidencePath=$file;ReviewedVersion=('a'*40);Python=$Python}
 $one=(& $planner @argsPlan)|ConvertFrom-Json
 $two=(& $planner @argsPlan)|ConvertFrom-Json
 if($one.status -cne 'PLAN_ONLY' -or $one.execution_authorized -ne $false -or $one.physical_ready -ne $false -or
    @($one.scenarios).Count -ne 8 -or (($one|ConvertTo-Json -Depth 15 -Compress) -cne ($two|ConvertTo-Json -Depth 15 -Compress))){throw 'Invalid plan'}
 if((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -cne $before){throw 'Input modified'}
 $count++
}
foreach($case in @('apply','invalid')){
 $blocked=$false
 if($case -eq 'invalid'){[IO.File]::WriteAllText($file,'{invalid')}
 try {if($case -eq 'apply'){& $planner @argsPlan -Apply|Out-Null}else{& $planner @argsPlan|Out-Null}} catch {$blocked=$true}
 if(!$blocked){throw 'Unsafe execution/input accepted'}
 $global:LASTEXITCODE=0;$count++
}
Write-Output "Physical plan safety fixtures passed: $count; no executor or host probes"
