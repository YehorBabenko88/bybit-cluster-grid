#Requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference='Stop'
$core=Join-Path $PSScriptRoot '../isolated-deployment-core.ps1'
if(!(Test-Path -LiteralPath $core)){throw 'ISOLATED_ADAPTER_MISSING'}
. $core
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('grid-isolated-'+[guid]::NewGuid().ToString('N'))
$parent=Join-Path $fixture 'GridLab';[void][IO.Directory]::CreateDirectory($parent)
$realPolicy=${function:Assert-GridLabStagingPolicy}
$global:LabTaskCalls=0
$global:LabCase='valid';$global:LabProbes=0;$global:LabPolicy=0
function Get-ScheduledTask {[CmdletBinding()]param()
 $global:LabProbes++;$global:LabTaskCalls++
 if($global:LabCase -eq 'late-active' -and $global:LabTaskCalls -ge 3){[pscustomobject]@{TaskName='BybitClusterGridCoordinator';State='Running'}}
 if($global:LabCase -eq 'task-error'){throw 'PRIVATE_PROVIDER_SECRET'}
 if($global:LabCase -eq 'unknown-action'){[pscustomobject]@{TaskName='UnrelatedName';State='Ready';Actions=@('opaque')}}
 if($global:LabCase -eq 'alternate-task'){[pscustomobject]@{TaskName='UnrelatedName';State='Ready';Actions=@([pscustomobject]@{Execute='python.exe';Arguments=('C:\x.py --data '+$global:CurrentPlan.root);WorkingDirectory='C:\'})}}
 if($global:LabCase -eq 'task'){[pscustomobject]@{TaskName=$global:CurrentPlan.tasks[0];State='Disabled'}}
 if($global:LabCase -eq 'active'){[pscustomobject]@{TaskName='BybitClusterGridAgent';State='Running'}}
}
function Get-CimInstance {[CmdletBinding()]param($ClassName,$OperationTimeoutSec,$Filter)
 $global:LabProbes++
 if($global:LabCase -eq 'cim-error'){throw 'PRIVATE_PROVIDER_SECRET'}
 switch($ClassName){
 'Win32_ComputerSystem' {[pscustomobject]@{Name= $(if($global:LabCase -eq 'production'){'LS5'}else{'LAB0'})}}
 'Win32_LogicalDisk' {[pscustomobject]@{DriveType=$(if($global:LabCase -eq 'network-drive'){4}else{3})}}
 'Win32_Process' {if($global:LabCase -eq 'unknown'){[pscustomobject]@{Name='postgres.exe';CommandLine=$null}}elseif($global:LabCase -eq 'process'){[pscustomobject]@{Name='python.exe';CommandLine='python -m grid.worker'}}else{[pscustomobject]@{Name='System';CommandLine=$null}}}
 'Win32_Service' {if($global:LabCase -eq 'service-error'){throw 'PRIVATE_PROVIDER_SECRET'};[pscustomobject]@{Name='UnrelatedService';PathName='C:\unrelated.exe'}}
 default {throw 'UNEXPECTED_CIM'}
 }
}
function Get-NetTCPConnection {[CmdletBinding()]param()
 $global:LabProbes++
 if($global:LabCase -eq 'tcp-error'){throw 'PRIVATE_PROVIDER_SECRET'}
 if($global:LabCase -eq 'port'){[pscustomobject]@{LocalPort=23001;LocalAddress='127.0.0.1'}}
}
function Get-NetUDPEndpoint {[CmdletBinding()]param()
 $global:LabProbes++
 if($global:LabCase -eq 'udp-error'){throw 'PRIVATE_PROVIDER_SECRET'}
 if($global:LabCase -eq 'udp-port'){[pscustomobject]@{LocalPort=23002;LocalAddress='::'}}
}
function Assert-GridLabStagingPolicy {param($Plan) $global:LabPolicy++;if($global:LabCase -eq 'policy'){throw 'PRIVATE_GITHUB_SECRET'}}
function Check([bool]$Condition,[string]$Message){if(!$Condition){throw $Message}}
function Plan([string]$Run){New-GridLabPlan -LabParent $parent -RunId $Run -NodeId LAB0 -Role CONTROL -Version ('a'*40) -Branch audit/codex-lab-candidate -PostgresPort 23001 -CoordinatorPort 23002}
function Block([scriptblock]$Action){$blocked=$false;try{& $Action|Out-Null}catch{$blocked=$true;Check (!$_.Exception.Message.Contains('PRIVATE')) 'Diagnostics leaked'};Check $blocked 'Unsafe operation accepted'}
$p=Plan ('1'*32);$global:CurrentPlan=$p
Check ($p.root -eq (Join-Path $parent (('1'*32)+'_LAB0'))) 'Wrong isolation root'
Check ($p.tasks[0] -eq ('BybitClusterGridLab_'+('1'*32)+'_LAB0_Agent')) 'Task collision risk'
Check ($global:LabProbes -eq 0 -and $global:LabPolicy -eq 0) 'Plan probed host'
Block {Invoke-GridLabPreparation -Plan $p -Mode Prepare -Approval ''}
Check (!(Test-Path -LiteralPath $p.root)) 'Unapproved preparation wrote files'
$count=2
foreach($case in @('task','active','task-error','cim-error','service-error','unknown','process','production','port','udp-port','tcp-error','udp-error','policy','late-active','alternate-task','unknown-action','network-drive')){
 $global:LabCase=$case;$global:LabTaskCalls=0
 Block {Invoke-GridLabPreparation -Plan $p -Mode Prepare -Approval ('PREPARE:'+$p.plan_sha256)}
 Check (!(Test-Path -LiteralPath $p.root)) ('Negative case wrote files: '+$case);$count++
}
$global:LabCase='valid'
$r=Invoke-GridLabPreparation -Plan $p -Mode Prepare -Approval ('PREPARE:'+$p.plan_sha256)
Check ($r.status -eq 'PREPARED_OFFLINE' -and !$r.activation_authorized) 'Preparation activated runtime'
Check ([IO.Directory]::Exists((Join-Path $p.root 'postgres\data'))) 'Dedicated PGDATA missing'
Check ([IO.Directory]::GetFileSystemEntries((Join-Path $p.root 'postgres\data')).Count -eq 0) 'Database initialized unexpectedly'
Check ((Get-Content (Join-Path $p.root 'postgresql.conf.template') -Raw) -match 'port = 23001') 'Wrong PG port'
Check (!(Test-Path (Join-Path $p.root 'current.version'))) 'Release pointer created'
$before=(Get-FileHash (Join-Path $p.root 'owner.jsonl')).Hash
Block {Invoke-GridLabPreparation -Plan $p -Mode Prepare -Approval ('PREPARE:'+$p.plan_sha256)}
Check ((Get-FileHash (Join-Path $p.root 'owner.jsonl')).Hash -eq $before) 'Retry modified journal'
$r=Invoke-GridLabPreparation -Plan $p -Mode Rollback -Approval ('RETIRE:'+$p.plan_sha256)
Check ($r.status -eq 'RETIRED_PRESERVED') 'Rollback failed'
$before=(Get-FileHash (Join-Path $p.root 'owner.jsonl')).Hash
$r=Invoke-GridLabPreparation -Plan $p -Mode Rollback -Approval ('RETIRE:'+$p.plan_sha256)
Check ((Get-FileHash (Join-Path $p.root 'owner.jsonl')).Hash -eq $before) 'Repeated rollback mutated journal'
Check (Test-Path (Join-Path $p.root 'postgresql.conf.template')) 'Rollback deleted resource'
$count+=4
# Inject failure at a real owned file creation boundary; preserve partial output.
$realWrite=${function:Write-GridLabNewFile}
function Write-GridLabNewFile {param($Path,$Text)
 if($Path.EndsWith('isolated.env.template')){throw 'INJECTED_WRITE_FAILURE'}
 & $realWrite -Path $Path -Text $Text
}
$partial=Plan ('2'*32);$global:CurrentPlan=$partial
Block {Invoke-GridLabPreparation -Plan $partial -Mode Prepare -Approval ('PREPARE:'+$partial.plan_sha256)}
Check (Test-Path (Join-Path $partial.root 'owner.jsonl')) 'Partial ownership evidence lost'
Block {Invoke-GridLabPreparation -Plan $partial -Mode Prepare -Approval ('PREPARE:'+$partial.plan_sha256)}
Set-Item function:Write-GridLabNewFile $realWrite
$r=Invoke-GridLabPreparation -Plan $partial -Mode Rollback -Approval ('RETIRE:'+$partial.plan_sha256)
Check ($r.status -eq 'RETIRED_PRESERVED') 'Partial rollback failed'
$count+=3
# Existing unknown directory and modified owned files are never adopted.
$foreign=Plan ('3'*32);[void][IO.Directory]::CreateDirectory($foreign.root);$global:CurrentPlan=$foreign
Block {Invoke-GridLabPreparation -Plan $foreign -Mode Prepare -Approval ('PREPARE:'+$foreign.plan_sha256)}
Block {Invoke-GridLabPreparation -Plan $foreign -Mode Rollback -Approval ('RETIRE:'+$foreign.plan_sha256)}
[IO.File]::WriteAllText((Join-Path $p.root 'tasks.plan.json'),'corrupt')
$global:CurrentPlan=$p
Block {Invoke-GridLabPreparation -Plan $p -Mode Rollback -Approval ('RETIRE:'+$p.plan_sha256)}
$count+=3
# PlanOnly validates without host probes and binds every effect to exact plan approval.
foreach($bad in @('branch','same-port','reserved-port','node','parent','mixed-parent','alias-parent','changed-plan')){
 if($bad -eq 'changed-plan'){
  $changed=Plan ('4'*32);$changed.root='C:\ProgramData\BybitClusterGrid'
  Block {Invoke-GridLabPreparation -Plan $changed -Mode Prepare -Approval ('PREPARE:'+$changed.plan_sha256)}
 }else{
  $argsPlan=@{LabParent=$parent;RunId=('4'*32);NodeId='LAB0';Version=('a'*40);Branch='audit/codex-lab-candidate';PostgresPort=23001;CoordinatorPort=23002}
  if($bad -eq 'branch'){$argsPlan.Branch='audit/physical-deployment-harness'}
  if($bad -eq 'same-port'){$argsPlan.CoordinatorPort=23001}
  if($bad -eq 'reserved-port'){$argsPlan.PostgresPort=55433}
  if($bad -eq 'node'){$argsPlan.NodeId='LS7'}
  if($bad -eq 'parent'){$argsPlan.LabParent='C:\ProgramData\GridLab'}
  if($bad -eq 'mixed-parent'){$argsPlan.LabParent='C:\safe/../ProgramData/GridLab'}
  if($bad -eq 'alias-parent'){$argsPlan.LabParent='C:\PROGRA~1\GridLab'}
  Block {New-GridLabPlan @argsPlan}
 }
 $count++
}
# Real path redirection in an owned fixture; no host provider is consulted.
$link=Join-Path $fixture 'redirect'
New-Item -ItemType Junction -Path $link -Target $fixture -ErrorAction Stop|Out-Null
$redirect=New-GridLabPlan -LabParent (Join-Path $link 'GridLab') -RunId ('5'*32) -NodeId LAB0 -Version ('a'*40) -Branch audit/codex-lab-candidate
$global:CurrentPlan=$redirect
Block {Invoke-GridLabPreparation -Plan $redirect -Mode Prepare -Approval ('PREPARE:'+$redirect.plan_sha256)}
$count++
# Use the REAL staging script with only GitHub I/O mocked. Failed latest gate must block before resource writes.
Set-Item function:Assert-GridLabStagingPolicy $realPolicy
function Get-Command {param($Name,$ErrorAction) [pscustomobject]@{Source='Invoke-LabFixtureGitHub'}}
function Invoke-LabFixtureGitHub {
 $global:LASTEXITCODE=0
 if($args[0] -ne 'api'){throw 'FIXTURE_FORBIDS_MUTATION'}
 if($args[1] -like '*/branches/*'){@{commit=@{sha=('a'*40)}}|ConvertTo-Json -Depth 5;return}
 $runs=@('preflight','windows-bundle','commissioning-manifest','composed-safety-gate','windows-commissioning')|ForEach-Object {
  @{name=$_;head_sha=('a'*40);head_branch='audit/codex-lab-candidate';event='pull_request';status='completed';conclusion=$(if($global:LabBadGate -and $_ -eq 'windows-commissioning'){'failure'}else{'success'});run_number=1;id=1}
 }
 @{workflow_runs=@($runs)}|ConvertTo-Json -Depth 6
}
$policyPlan=Plan ('6'*32);$global:CurrentPlan=$policyPlan
$global:LabBadGate=$true
Block {Invoke-GridLabPreparation -Plan $policyPlan -Mode Prepare -Approval ('PREPARE:'+$policyPlan.plan_sha256)}
Check (!(Test-Path -LiteralPath $policyPlan.root)) 'Failed policy created resources'
$global:LabBadGate=$false
$r=Invoke-GridLabPreparation -Plan $policyPlan -Mode Prepare -Approval ('PREPARE:'+$policyPlan.plan_sha256)
Check ($r.status -eq 'PREPARED_OFFLINE') 'Existing staging policy not reused'
$count+=2
$entry=Join-Path $PSScriptRoot '../isolated-deployment.ps1'
$cli=& $entry -LabParent $parent -RunId ('7'*32) -NodeId LAB0 -Version ('a'*40) -Branch audit/codex-lab-candidate|ConvertFrom-Json
Check ($cli.status -eq 'PLAN_ONLY' -and !(Test-Path -LiteralPath $cli.plan.root)) 'CLI default changed resources'
$count++
# Real commissioning integrity validator, fake release bytes, no target execution or SQL.
$release=Join-Path $fixture 'release';[void][IO.Directory]::CreateDirectory((Join-Path $release 'grid'))
$hashes=[ordered]@{}
foreach($name in @('run_coordinator.py','grid/control_runtime.py','grid/collection_ownership.py','grid/retention.py')){
 $path=Join-Path $release $name
 [IO.File]::WriteAllText($path,'raise RuntimeError("TARGET_MUST_NOT_RUN")')
 $hashes[$name]=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
[IO.File]::WriteAllText((Join-Path $release 'release-manifest.json'),(@{version=('a'*40);files=$hashes}|ConvertTo-Json -Depth 5))
$checker=Join-Path $PSScriptRoot '../isolated_release_preflight.py'
$proof=(& $Python -B $checker --release-dir $release --commit ('a'*40) --role CONTROL)|ConvertFrom-Json
Check ($LASTEXITCODE -eq 0 -and $proof.release.status -eq 'PASS' -and !$proof.database_checked -and !$proof.activation_authorized) 'Integrity preflight failed'
[IO.File]::WriteAllText((Join-Path $release 'grid/control_runtime.py'),'tampered')
$proof=(& $Python -B $checker --release-dir $release --commit ('a'*40) --role CONTROL)|ConvertFrom-Json
Check ($LASTEXITCODE -eq 2 -and $proof.release.status -eq 'BLOCKED') 'Corrupt release accepted'
$global:LASTEXITCODE=0
$count+=2
# Revalidate the entire owned tree after the final inventory, not only journal bytes.
$realHost=${function:Assert-GridLabHost}
foreach($damage in @('changed-file','foreign-file')){
 $run=if($damage -eq 'changed-file'){'8'*32}else{'9'*32}
 $treePlan=Plan $run;$global:CurrentPlan=$treePlan
 [void](Invoke-GridLabPreparation -Plan $treePlan -Mode Prepare -Approval ('PREPARE:'+$treePlan.plan_sha256))
 $saved=[IO.File]::ReadAllText((Join-Path $treePlan.root 'owner.jsonl'))
 $global:LabHostCount=0;$global:LabDamage=$damage
 function Assert-GridLabHost {param($Plan)
  & $realHost -Plan $Plan;$global:LabHostCount++
  if($global:LabHostCount -eq 2){
   $name=if($global:LabDamage -eq 'changed-file'){'tasks.plan.json'}else{'foreign.txt'}
   [IO.File]::WriteAllText((Join-Path $Plan.root $name),'FOREIGN_CONTENT')
  }
 }
 Block {Invoke-GridLabPreparation -Plan $treePlan -Mode Rollback -Approval ('RETIRE:'+$treePlan.plan_sha256)}
 Check ([IO.File]::ReadAllText((Join-Path $treePlan.root 'owner.jsonl')) -ceq $saved) 'Tree race appended retirement'
 Set-Item function:Assert-GridLabHost $realHost
 $count++
}
$global:CurrentPlan=$policyPlan
# Mutation during the final host check must not append to changed ownership evidence.
$realHost=${function:Assert-GridLabHost};$global:LabHostCount=0
function Assert-GridLabHost {param($Plan)
 & $realHost -Plan $Plan
 $global:LabHostCount++
 if($global:LabHostCount -eq 2){[IO.File]::WriteAllText((Join-Path $Plan.root 'owner.jsonl'),'FOREIGN_JOURNAL')}
}
$record=Join-Path $policyPlan.root 'owner.jsonl'
Block {Invoke-GridLabPreparation -Plan $policyPlan -Mode Rollback -Approval ('RETIRE:'+$policyPlan.plan_sha256)}
Check ([IO.File]::ReadAllText($record) -ceq 'FOREIGN_JOURNAL') 'Rollback appended to changed journal'
Set-Item function:Assert-GridLabHost $realHost
# A hardlinked receipt must never be appended through another resource's name.
[IO.File]::WriteAllText($record,((Get-GridLabRecord $policyPlan 'PREPARED')+(Get-GridLabRecord $policyPlan 'COMMITTED')))
$other=Join-Path $fixture 'foreign-receipt.txt'
New-Item -ItemType HardLink -Path $other -Target $record -ErrorAction Stop|Out-Null
$before=[IO.File]::ReadAllText($other)
Block {Invoke-GridLabPreparation -Plan $policyPlan -Mode Rollback -Approval ('RETIRE:'+$policyPlan.plan_sha256)}
Check ([IO.File]::ReadAllText($other) -ceq $before) 'Rollback changed hardlinked resource'
$count+=2
Write-Output "Isolated adapter fixtures passed: $count; host providers and staging mocked; files confined to GUID temp fixture; no SQL, tasks, services or runtime started"
