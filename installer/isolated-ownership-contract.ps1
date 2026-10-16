#Requires -Version 5.1
# Pure byte-contract diagnostic. NOT a filesystem/native ownership verifier.
# No host providers, file reads, native compilation, locks or consumer callbacks.
. (Join-Path $PSScriptRoot 'isolated-deployment-core.ps1')
function Test-GridLabOwnershipBytes {
 [CmdletBinding()]
 param($ExpectedPlan,$ExpectedPlanSha256,$ExpectedCommit,$Files,$Directories)
 $result=[ordered]@{schema=1;kind='OWNERSHIP_CONTRACT_DIAGNOSTIC';status='BLOCKED';
  byte_contract='REJECTED';code='GRID_OWNERSHIP_INPUT_INVALID';
  execution_authorized=$false;physical_ready=$false;
  blockers=@('LOCAL_NATIVE_HANDLE_SESSION_NOT_IMPLEMENTED','SCHEMA2_DISABLED')}
 try {
  if($ExpectedPlan -isnot [pscustomobject] -or $ExpectedPlanSha256 -isnot [string] -or
     $ExpectedPlanSha256 -cnotmatch '^[0-9a-f]{64}$' -or $ExpectedCommit -isnot [string] -or
     $ExpectedCommit -cnotmatch '^[0-9a-f]{40}$' -or $ExpectedCommit -eq ('0'*40)) {throw 'GRID_OWNERSHIP_INTENT_INVALID'}
  # Validate data shape BEFORE binding or serializing: ConvertTo-Json can run
  # nested ScriptProperty getters, and string parameter coercion can call code.
  $strings=@('kind','parent','root','run_id','node_id','role','version','branch','database','staging_policy','rollback','plan_sha256')
  $numbers=@('schema','postgres_port','coordinator_port')
  $booleans=@('activation_authorized','database_initialization_authorized','tasks_registered')
  $arrays=@('tasks','blockers')
  $properties=@($ExpectedPlan.PSObject.Properties)
  if($properties.Count -ne 20){throw 'GRID_OWNERSHIP_INTENT_INVALID'}
  foreach($property in $properties){
   if($property.MemberType -ne [Management.Automation.PSMemberTypes]::NoteProperty){throw 'GRID_OWNERSHIP_INTENT_INVALID'}
   $name=$property.Name;$value=$property.Value
   if($name -cin $strings){
    if($value -isnot [string] -or $value.Length -gt 2048){throw 'GRID_OWNERSHIP_INTENT_INVALID'}
   }elseif($name -cin $numbers){
    if($value -isnot [int] -and $value -isnot [long]){throw 'GRID_OWNERSHIP_INTENT_INVALID'}
   }elseif($name -cin $booleans){
    if($value -isnot [bool]){throw 'GRID_OWNERSHIP_INTENT_INVALID'}
   }elseif($name -cin $arrays){
    if($value -isnot [Array] -or $value.Rank -ne 1 -or $value.Length -gt 32){throw 'GRID_OWNERSHIP_INTENT_INVALID'}
    foreach($element in $value){if($element -isnot [string] -or $element.Length -gt 2048){throw 'GRID_OWNERSHIP_INTENT_INVALID'}}
   }else{throw 'GRID_OWNERSHIP_INTENT_INVALID'}
  }
  $plan=New-GridLabPlan -LabParent $ExpectedPlan.parent -RunId $ExpectedPlan.run_id -NodeId $ExpectedPlan.node_id -Role $ExpectedPlan.role -Version $ExpectedPlan.version -Branch $ExpectedPlan.branch -PostgresPort $ExpectedPlan.postgres_port -CoordinatorPort $ExpectedPlan.coordinator_port
  $canonical=$plan|ConvertTo-Json -Depth 10 -Compress
  if($canonical -cne ($ExpectedPlan|ConvertTo-Json -Depth 10 -Compress) -or
     $plan.plan_sha256 -cne $ExpectedPlanSha256 -or $plan.version -cne $ExpectedCommit){throw 'GRID_OWNERSHIP_INTENT_MISMATCH'}
  $expected=Get-GridLabFiles $plan
  $expected['owner.jsonl']=(Get-GridLabRecord $plan PREPARED)+(Get-GridLabRecord $plan COMMITTED)
  if($Files -isnot [Collections.IDictionary] -or $Files.Count -ne $expected.Count){throw 'GRID_OWNERSHIP_FILE_SET_INVALID'}
  foreach($name in $Files.Keys){
   if($name -isnot [string] -or $name -cnotin @($expected.Keys)){throw 'GRID_OWNERSHIP_FILE_SET_INVALID'}
   $bytes=$Files[$name];$limit=if($name -ceq 'owner.jsonl'){4096}else{65536}
   if($bytes -isnot [byte[]] -or $bytes.Length -gt $limit){throw 'GRID_OWNERSHIP_FILE_BYTES_INVALID'}
   $wanted=[Text.Encoding]::UTF8.GetBytes($expected[$name])
   if($bytes.Length -ne $wanted.Length -or [Convert]::ToBase64String($bytes) -cne [Convert]::ToBase64String($wanted)){
    if($name -ceq 'owner.jsonl'){throw 'GRID_OWNERSHIP_JOURNAL_BYTES_INVALID'}
    throw 'GRID_OWNERSHIP_TEMPLATE_BYTES_INVALID'
   }
  }
  $expectedDirs=@('releases','data','data\wal','postgres','postgres\data')
  if($Directories -isnot [Array] -or $Directories.Count -ne $expectedDirs.Count){throw 'GRID_OWNERSHIP_DIRECTORY_SET_INVALID'}
  $seen=@()
  foreach($directory in $Directories){
   if($directory -isnot [string] -or $directory -cnotin $expectedDirs -or $directory -cin $seen){throw 'GRID_OWNERSHIP_DIRECTORY_SET_INVALID'}
   $seen+=,$directory
  }
  # Matching untrusted bytes never imply native identity, ACL, mutex or freshness.
  # No PGDATA path or transferable capability is exported, even on this branch.
  $result.byte_contract='MATCHED_UNAUTHENTICATED'
  $result.code='GRID_OWNERSHIP_NATIVE_SESSION_REQUIRED'
 }catch{
  if($_.Exception.Message -cmatch '^GRID_OWNERSHIP_[A-Z_]+$'){$result.code=$_.Exception.Message}
 }
 [pscustomobject]$result
}
