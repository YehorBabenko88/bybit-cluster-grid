#Requires -Version 5.1
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot '..\installer\isolated-ownership-contract.ps1')
# Pure producers only: no Prepare, Rollback, host inventory or resource access.
function Assert-GridLabHost { throw 'AUDIT_HOST_ACCESS_FORBIDDEN' }
function Assert-GridLabPhysical { throw 'AUDIT_HOST_ACCESS_FORBIDDEN' }
function Invoke-GridLabPreparation { throw 'AUDIT_MUTATION_FORBIDDEN' }
$p=New-GridLabPlan -LabParent 'C:\AuditOnly\GridLab' -RunId ('a'*32) -NodeId LAB01 -Version ('b'*40) -Branch audit/codex-contract-review
$files=Get-GridLabFiles $p
$prepared=Get-GridLabRecord $p PREPARED
$committed=Get-GridLabRecord $p COMMITTED
$retired=Get-GridLabRecord $p RETIRED
$files['owner.jsonl']=$prepared+$committed
$bytes=[ordered]@{}
foreach($name in $files.Keys){$bytes[$name]=[Text.Encoding]::UTF8.GetBytes($files[$name])}
$dirs=@('releases','data','data\wal','postgres','postgres\data')
$assessment=Test-GridLabOwnershipBytes -ExpectedPlan $p -ExpectedPlanSha256 $p.plan_sha256 -ExpectedCommit $p.version -Files $bytes -Directories $dirs
$rejections=[ordered]@{}
$mutations=[ordered]@{
 pretty=($prepared+$committed).Replace(':',': ')
 reordered=(([ordered]@{state='PREPARED';plan_sha256=$p.plan_sha256;schema=1}|ConvertTo-Json -Compress)+"`n"+$committed)
 crlf=($prepared+$committed).Replace("`n","`r`n")
 escaped=($prepared+$committed).Replace('PREPARED','\u0050REPARED')
 partial=$prepared
 retired=$prepared+$committed+$retired
 duplicate=$prepared+$prepared+$committed
 torn=($prepared+$committed).Substring(0,($prepared+$committed).Length-2)
}
foreach($name in $mutations.Keys){
 $bytes['owner.jsonl']=[Text.Encoding]::UTF8.GetBytes($mutations[$name])
 $rejections[$name]=Test-GridLabOwnershipBytes -ExpectedPlan $p -ExpectedPlanSha256 $p.plan_sha256 -ExpectedCommit $p.version -Files $bytes -Directories $dirs
}
$out=[ordered]@{plan=$p;prepared=$prepared;committed=$committed;retired=$retired;files=$files;directories=$dirs;assessment=$assessment;rejections=$rejections}
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($out|ConvertTo-Json -Depth 15 -Compress)))
