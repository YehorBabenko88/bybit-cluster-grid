#Requires -Version 5.1
param([switch]$EmitReport)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../isolated-deployment-core.ps1')
$module=Join-Path $PSScriptRoot '../isolated-ownership-contract.ps1'
if(!(Test-Path -LiteralPath $module)){throw 'OWNERSHIP_BYTE_CONTRACT_MISSING'}
. $module
$plan=New-GridLabPlan -LabParent 'C:\GridLab' -RunId ('a'*32) -NodeId LAB01 -Role CONTROL -Version ('b'*40) -Branch audit/codex-contract
function New-Evidence {
 $files=[ordered]@{}
 foreach($name in (Get-GridLabFiles $plan).Keys){$files[$name]=[Text.Encoding]::UTF8.GetBytes((Get-GridLabFiles $plan)[$name])}
 $files['owner.jsonl']=[Text.Encoding]::UTF8.GetBytes((Get-GridLabRecord $plan PREPARED)+(Get-GridLabRecord $plan COMMITTED))
 @{Files=$files;Directories=@('releases','data','data\wal','postgres','postgres\data')}
}
# Any accidental host/native provider use must fail this in-memory suite.
$script:OwnershipProbes=0
function Fail-OwnershipProbe {$script:OwnershipProbes++;throw 'UNEXPECTED_OWNERSHIP_HOST_PROBE'}
function Get-CimInstance {Fail-OwnershipProbe}
function Get-ScheduledTask {Fail-OwnershipProbe}
function Get-NetTCPConnection {Fail-OwnershipProbe}
function Get-NetUDPEndpoint {Fail-OwnershipProbe}
function Get-Acl {Fail-OwnershipProbe}
function Get-Item {Fail-OwnershipProbe}
function Get-ChildItem {Fail-OwnershipProbe}
function Add-Type {Fail-OwnershipProbe}
function Start-Process {Fail-OwnershipProbe}
$count=0
function Check($condition,[string]$code){if(!$condition){throw $code}}
function Assess($e,$intent=$plan,$hash=$plan.plan_sha256,$commit=$plan.version){
 Test-GridLabOwnershipBytes -ExpectedPlan $intent -ExpectedPlanSha256 $hash -ExpectedCommit $commit -Files $e.Files -Directories $e.Directories
}
function Check-Blocked($r){
 Check ($r.status -ceq 'BLOCKED' -and $r.execution_authorized -eq $false -and $r.physical_ready -eq $false) 'OWNERSHIP_AUTHORITY_LEAK'
 Check ($r.PSObject.Properties.Name -notcontains 'data_root' -and $r.PSObject.Properties.Name -notcontains 'pgdata') 'OWNERSHIP_PATH_EXPORT'
}
$r=Assess (New-Evidence);Check-Blocked $r
Check ($r.byte_contract -ceq 'MATCHED_UNAUTHENTICATED' -and $r.code -ceq 'GRID_OWNERSHIP_NATIVE_SESSION_REQUIRED') 'CANONICAL_BYTES_NOT_MATCHED'
$count++
foreach($case in @('prepared','retired','prepared-retired','torn','foreign','duplicate','reordered','crlf','bom','missing-newline','json-whitespace')){
 $e=New-Evidence;$prepared=Get-GridLabRecord $plan PREPARED;$committed=Get-GridLabRecord $plan COMMITTED;$retired=Get-GridLabRecord $plan RETIRED
 $journal=switch($case){
  'prepared'{$prepared};'retired'{$prepared+$committed+$retired};'prepared-retired'{$prepared+$retired}
  'torn'{$prepared+$committed.Substring(0,$committed.Length-2)};'foreign'{$prepared.Replace($plan.plan_sha256,('f'*64))+$committed}
  'duplicate'{$prepared+$committed+$committed};'reordered'{$committed+$prepared};'crlf'{($prepared+$committed).Replace("`n","`r`n")}
  'bom'{[char]0xfeff+$prepared+$committed};'missing-newline'{($prepared+$committed).TrimEnd("`n")};'json-whitespace'{' '+$prepared+$committed}
 }
 $e.Files['owner.jsonl']=[Text.Encoding]::UTF8.GetBytes($journal)
 $r=Assess $e;Check-Blocked $r;Check ($r.code -ceq 'GRID_OWNERSHIP_JOURNAL_BYTES_INVALID') ('JOURNAL_ACCEPTED_'+$case);$count++
}
foreach($case in @('missing-file','foreign-file','pgdata-file','case-file','changed-template','plan-duplicate','plan-reordered','plan-bom','string-bytes','large-file','large-journal','empty-dirs','extra-dir','missing-dir','duplicate-dir','case-dir','nonstring-dir')){
 $e=New-Evidence
 switch($case){
  'missing-file'{$e.Files.Remove('tasks.plan.json')};'foreign-file'{$e.Files['foreign.txt']=[byte[]]@(1)}
  'pgdata-file'{$e.Files['postgres\data\PG_VERSION']=[byte[]]@(49,54)}
  'case-file'{$e.Files.Remove('tasks.plan.json');$e.Files['TASKS.plan.json']=[byte[]]@(1)}
  'changed-template'{$e.Files['postgresql.conf.template']=[Text.Encoding]::UTF8.GetBytes('data_directory=foreign')}
  'plan-duplicate'{$e.Files['deployment-plan.json']=[Text.Encoding]::UTF8.GetBytes('{"schema":1,"schema":1}')}
  'plan-reordered'{$e.Files['deployment-plan.json']=[Text.Encoding]::UTF8.GetBytes('{"kind":"ISOLATED_PREPARATION","schema":1}')}
  'plan-bom'{$e.Files['deployment-plan.json']=[byte[]](@(239,187,191)+$e.Files['deployment-plan.json'])}
  'string-bytes'{$e.Files['deployment-plan.json']='not bytes'}
  'large-file'{$e.Files['tasks.plan.json']=New-Object byte[] 65537}
  'large-journal'{$e.Files['owner.jsonl']=New-Object byte[] 4097}
  'empty-dirs'{$e.Directories=@()};'extra-dir'{$e.Directories+=@('foreign')};'missing-dir'{$e.Directories=@('data')}
  'duplicate-dir'{$e.Directories+=@('data')};'case-dir'{$e.Directories[0]='Releases'};'nonstring-dir'{$e.Directories[0]=1}
 }
 $r=Assess $e;Check-Blocked $r;Check ($r.byte_contract -ceq 'REJECTED') ('UNSAFE_BYTES_ACCEPTED_'+$case);$count++
}
foreach($field in @('root','parent','run_id','node_id','role','version','branch','postgres_port','coordinator_port','plan_sha256','activation_authorized')){
 $intent=$plan|ConvertTo-Json -Depth 10 -Compress|ConvertFrom-Json
 switch($field){
  'root'{$intent.root+='-copy'};'parent'{$intent.parent='C:\Other\GridLab'};'run_id'{$intent.run_id='c'*32}
  'node_id'{$intent.node_id='LAB02'};'role'{$intent.role='WORKER'};'version'{$intent.version='c'*40}
  'branch'{$intent.branch='main'};'postgres_port'{$intent.postgres_port=25001};'coordinator_port'{$intent.coordinator_port=25002}
  'plan_sha256'{$intent.plan_sha256='c'*64};'activation_authorized'{$intent.activation_authorized=$true}
 }
 $r=Assess (New-Evidence) $intent;Check-Blocked $r;Check ($r.byte_contract -ceq 'REJECTED') ('INTENT_NOT_BOUND_'+$field);$count++
}
foreach($case in @('wrong-hash','wrong-commit','bool-port','extra-plan-field','null-plan','null-files','null-dirs','oversized-tree')){
 $e=New-Evidence;$intent=$plan|ConvertTo-Json -Depth 10 -Compress|ConvertFrom-Json;$hash=$plan.plan_sha256;$commit=$plan.version
 switch($case){
  'wrong-hash'{$hash='c'*64};'wrong-commit'{$commit='c'*40};'bool-port'{$intent.postgres_port=$true}
  'extra-plan-field'{$intent|Add-Member NoteProperty native_proof $true};'null-plan'{$intent=$null}
  'null-files'{$e.Files=$null};'null-dirs'{$e.Directories=$null}
  'oversized-tree'{1..100|ForEach-Object {$e.Files["extra$_.bin"]=[byte[]]@(0)}}
 }
 $r=Assess $e $intent $hash $commit;Check-Blocked $r;Check ($r.byte_contract -ceq 'REJECTED') ('MALFORMED_ACCEPTED_'+$case);$count++
}
# Native/freshness flags have no accepted proof surface: unknown file claims reject.
foreach($claim in @('handles-held','hardlink-clear','reparse-clear','mapped-drive-clear','acl-protected','generic-rights-clear','native-api-success','fresh-snapshot','toctou-rechecked','mutex-held')){
 $e=New-Evidence;$e.Files[$claim]=[Text.Encoding]::UTF8.GetBytes('true')
 $r=Assess $e;Check-Blocked $r;Check ($r.byte_contract -ceq 'REJECTED') ('SERIALIZED_PROOF_ACCEPTED_'+$claim);$count++
}
foreach($case in @('nested-getter','coercion-method')){
 $script:OwnershipCallbacks=0
 $intent=$plan|ConvertTo-Json -Depth 10 -Compress|ConvertFrom-Json
 $executable=[pscustomobject]@{}
 if($case -eq 'nested-getter'){
  $executable|Add-Member ScriptProperty boom {$script:OwnershipCallbacks++;'PRIVATE'}
  $intent.tasks=$executable
 }else{
  $executable|Add-Member ScriptMethod ToString {$script:OwnershipCallbacks++;'C:\GridLab'} -Force
  $intent.parent=$executable
 }
 $r=Assess (New-Evidence) $intent;Check-Blocked $r
 Check ($script:OwnershipCallbacks -eq 0) ('EXECUTABLE_INTENT_INVOKED_'+$case)
 Check ($r.code -ceq 'GRID_OWNERSHIP_INTENT_INVALID') ('EXECUTABLE_INTENT_NOT_REJECTED_'+$case)
 $count++
}
Check ($script:OwnershipProbes -eq 0) 'HOST_PROVIDER_INVOKED'
if($EmitReport){[ordered]@{schema=1;cases=$count;canonical_assessment=(Assess (New-Evidence));plan_sha256=$plan.plan_sha256;providers_invoked=$script:OwnershipProbes}|ConvertTo-Json -Depth 10 -Compress;return}
Write-Output ("Ownership byte contract passed: "+$count+"; in-memory only; every assessment BLOCKED; no positive native ownership proof")
