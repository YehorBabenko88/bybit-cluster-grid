[CmdletBinding()]
param(
 [ValidateSet('Prepare','EphemeralCI')][string]$Mode='Prepare',
 [Parameter(Mandatory=$true)][string]$ArtifactRoot,
 [Parameter(Mandatory=$true)][string]$StageRoot,
 [Parameter(Mandatory=$true)][string]$UnifiedRoot,
 [Parameter(Mandatory=$true)][string]$UnifiedSourceHead,
 [Parameter(Mandatory=$true)][string]$UnifiedSourceTree,
 [Parameter(Mandatory=$true)][string]$CatalogSha256,
 [Parameter(Mandatory=$true)][string]$PreflightSha256,
 [Parameter(Mandatory=$true)][string]$SourceGuardSha256,
 [Parameter(Mandatory=$true)][string]$LibrarySha256,
 [Parameter(Mandatory=$true)][string]$NativeJobSha256,
 [switch]$AuthorizeEphemeralWindowsCI
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
# Minimal bootstrap boundary before importing the externally pinned local library.
function Assert-StageBootstrapPath([string]$Path) {
 if($Path -notmatch '^[A-Za-z]:\\' -or $Path.Contains('/') -or $Path.Substring(2).Contains(':') -or $Path.Contains('..')){throw 'PORTABLE_LOCAL_NAMESPACE_REQUIRED'}
 $full=[IO.Path]::GetFullPath($Path);$anchor=[IO.Path]::GetPathRoot($full)
 if([IO.DriveInfo]::new($anchor).DriveType -ne [IO.DriveType]::Fixed){throw 'PORTABLE_FIXED_DRIVE_REQUIRED'}
 $drive=Get-PSDrive -Name ($anchor.Substring(0,1)) -ErrorAction Stop
 if($drive.Provider.Name -cne 'FileSystem' -or $drive.Root.TrimEnd('\') -ine $anchor.TrimEnd('\')){throw 'PORTABLE_DRIVE_NAMESPACE_MISMATCH'}
 $list=New-Object 'System.Collections.Generic.List[string]';$cursor=$full
 while($cursor){$list.Add($cursor);$next=[IO.Path]::GetDirectoryName($cursor.TrimEnd('\'));if($next -eq $cursor){break};$cursor=$next}
 for($i=$list.Count-1;$i -ge 0;$i--){
  try{$item=Get-Item -LiteralPath $list[$i] -Force -ErrorAction Stop}catch [Management.Automation.ItemNotFoundException]{return}
  if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or ($i -ne 0 -and !$item.PSIsContainer)){throw 'PORTABLE_UNSAFE_ANCESTOR'}
 }
}
$library=Join-Path $PSScriptRoot 'PortableRuntime.psm1';Assert-StageBootstrapPath $library
if($LibrarySha256 -cnotmatch '^[a-f0-9]{64}$' -or (Get-FileHash -LiteralPath $library -Algorithm SHA256).Hash.ToLowerInvariant() -cne $LibrarySha256){throw 'PORTABLE_EXTERNAL_LIBRARY_PIN_REQUIRED'}
Import-Module $library -Force
Add-Type -AssemblyName System.IO.Compression
$catalogPath=Join-Path $UnifiedRoot 'unified_system\windows-toolchain.catalog.json'
$preflight=Join-Path $UnifiedRoot 'unified_system\package_preflight.py'
$guard=Join-Path $UnifiedRoot 'integration\source_guard.py'
$nativeJob=Join-Path $PSScriptRoot 'NativeJobProcess.cs'
foreach($path in @($ArtifactRoot,$UnifiedRoot,$catalogPath,$preflight,$guard,$nativeJob)){Assert-PortableLocalPath $path -MustExist}
Assert-PortableLocalPath $StageRoot
if($UnifiedSourceHead -cnotmatch '^[a-f0-9]{40}$' -or $UnifiedSourceTree -cnotmatch '^[a-f0-9]{40}$'){throw 'PORTABLE_EXTERNAL_SOURCE_ID_REQUIRED'}
if((Get-PortableHash $preflight 1048576) -cne $PreflightSha256 -or (Get-PortableHash $guard 1048576) -cne $SourceGuardSha256){throw 'PORTABLE_EXTERNAL_PREFLIGHT_PIN_MISMATCH'}
if($NativeJobSha256 -cnotmatch '^[a-f0-9]{64}$' -or (Get-PortableHash $nativeJob 65536) -cne $NativeJobSha256){throw 'PORTABLE_EXTERNAL_JOB_PIN_MISMATCH'}
$catalog=Read-PortableCatalog $catalogPath $CatalogSha256
$report=[ordered]@{schema='grid.portable-sdk-stage.v1';mode=$Mode;result='BLOCKED';scope='COMPONENT_SDK_TEST_ONLY';catalog_sha256=$CatalogSha256;source_head=$UnifiedSourceHead;source_tree=$UnifiedSourceTree;archives=@();required_unlocked=$catalog.required_unlocked;installation_closure=$false;global_status='NO_GO';publisher_authenticated=$false;execution_authority=$false;trading_authorized=$false;physical_deployment_allowed=$false;services='NOT_INSTALLED';physical='NOT_RUN';native_execution='NOT_RUN'}
$metadata=@{};[long]$totalExpanded=0;[long]$totalFiles=0
# Prepare is entirely read-only: all FIVE real pinned local archives are mandatory.
foreach($descriptor in $catalog.artifacts){
 $opened=$null
 try {
  $opened=Open-PortableArchive (Join-Path $ArtifactRoot $descriptor.filename) $descriptor
  $metadata[$descriptor.component]=$descriptor;$totalExpanded+=$opened.metadata.expanded_bytes;$totalFiles+=$opened.metadata.records.Count
  if($totalExpanded -gt 4294967296 -or $totalFiles -gt 40000){throw 'PORTABLE_TOTAL_RESOURCE_BUDGET'}
  $report.archives+=@{component=$descriptor.component;version=$descriptor.version;sha256=$descriptor.sha256;status='PINNED_BYTES_AND_ZIP_MATCH';expanded_bytes=$opened.metadata.expanded_bytes;entries=$opened.metadata.records.Count}
 } catch {
  $report.archives+=@{component=$descriptor.component;version=$descriptor.version;status='BLOCKED_MISSING_OR_INVALID'}
 } finally {if($null -ne $opened){Close-PortableArchive $opened}}
}
if(@($report.archives | Where-Object {$_.status -cne 'PINNED_BYTES_AND_ZIP_MATCH'}).Count -ne 0 -or $metadata.Count -ne 5){$report | ConvertTo-Json -Depth 12 -Compress;throw 'PORTABLE_INPUTS_BLOCKED'}
if($Mode -eq 'Prepare'){$report.result='PREPARED_INPUTS_ONLY';$report | ConvertTo-Json -Depth 12 -Compress;return}
$machine=[Environment]::MachineName.Split('.')[0].ToUpperInvariant()
if(!$AuthorizeEphemeralWindowsCI -or [Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $machine -in @('ADMINIT','LS5','PC4') -or !$env:RUNNER_TEMP){throw 'PORTABLE_EXPLICIT_HOSTED_TEST_REQUIRED'}
Assert-PortableLocalPath $env:RUNNER_TEMP -MustExist
$target=[IO.Path]::GetFullPath($StageRoot).TrimEnd('\');$temporary=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')+'\'
if(!$target.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase) -or [IO.Directory]::Exists($target) -or [IO.File]::Exists($target)){throw 'PORTABLE_FRESH_RUNNER_STAGE_REQUIRED'}
$volume=[IO.DriveInfo]::new([IO.Path]::GetPathRoot($target))
if($volume.AvailableFreeSpace -lt $totalExpanded+1073741824){throw 'PORTABLE_FREE_SPACE_BUDGET'}
[IO.Directory]::CreateDirectory($target) | Out-Null
Initialize-PortableJob $nativeJob $NativeJobSha256
$pgJob=$null
$inventory=@{};$pgStarted=$false;$pgData=$null;$pgCtl=$null;$pgCtlPin=$null;$working=$null;$failure=$null;$phase='INITIALIZE_STAGE'
function Extract-Component([string]$Name) {
 $opened=Open-PortableArchive (Join-Path $ArtifactRoot $metadata[$Name].filename) $metadata[$Name]
 try {foreach($file in (Expand-PortableArchive $opened (Join-Path $target $Name))){$inventory[$file.path]=$file}} finally {Close-PortableArchive $opened}
}
function Executable([string]$Relative) {
 if(!$inventory.ContainsKey($Relative)){throw 'PORTABLE_EXPECTED_EXECUTABLE_MISSING'}
 $file=Join-Path $target ($Relative.Replace('/','\'))
 if((Get-PortableHash $file 134217728) -cne $inventory[$Relative].sha256){throw 'PORTABLE_DERIVED_EXECUTABLE_PIN_MISMATCH'}
 # Test the real vendor payload, never a synthetic/fake PE substitute.
 $stream=[IO.File]::OpenRead($file)
 try {
  $header=New-Object byte[] 64;if($stream.Read($header,0,64) -ne 64 -or $header[0] -ne 77 -or $header[1] -ne 90){throw 'PORTABLE_PE_REQUIRED'}
  $offset=[BitConverter]::ToUInt32($header,60);if($offset -gt 1048576 -or $offset+6 -gt $stream.Length){throw 'PORTABLE_PE_HEADER_BUDGET'}
  $stream.Position=$offset;$pe=New-Object byte[] 6;if($stream.Read($pe,0,6) -ne 6 -or [BitConverter]::ToUInt32($pe,0) -ne 17744 -or [BitConverter]::ToUInt16($pe,4) -ne 34404){throw 'PORTABLE_X64_PE_REQUIRED'}
 } finally {$stream.Dispose()}
 return $file
}
function Run-Tool([string]$Relative,[string[]]$Arguments,[int]$Seconds=30) {
 $file=Executable $Relative
 return Invoke-PortableProcess $file $inventory[$Relative].sha256 $Arguments $working $Seconds
}
function Version-Tool([string]$Relative,[string]$Pattern,[string[]]$Arguments) {
 $result=Run-Tool $Relative $Arguments 20;$text=($result.stdout+' '+$result.stderr).Trim()
 if($text -notmatch $Pattern){throw 'PORTABLE_VERSION_MISMATCH'}
 return ($text -replace '\s+',' ').Substring(0,[Math]::Min(160,($text -replace '\s+',' ').Length))
}
function Write-PrivatePreflightDiagnostic([Exception]$Failure) {
 # Inspect already bounded private data only for the raw preflight invocation.
 # This is a failure diagnostic, never an alternate success/admission path.
 try {
  $node=$Failure;$private=$null
  for($depth=0;$null -ne $node -and $depth -lt 8;$depth++){
   if($node.Data.Contains('GridPortable.BoundedResult')){$private=$node.Data['GridPortable.BoundedResult'];break}
   $node=$node.InnerException
  }
  if($private -isnot [GridPortable.JobResult] -or $private.ExitCode -eq 0){return}
  if($private.Stdout.Length -gt 65536 -or $private.Stderr.Length -gt 65536){return}
  if($private.Stderr.Trim() -ceq 'PACKAGE_PREFLIGHT_REJECTED'){
   Write-Host '::error title=Raw preflight rejection::status=PACKAGE_PREFLIGHT_REJECTED';return
  }
  $payload=$private.Stdout | ConvertFrom-Json
  $keys=@('schema','scope','status','source_head','source_tree','integrity','installation_closure','services','native_execution','physical','execution_authority','trading_authorized','physical_deployment_allowed')
  if(@($payload.PSObject.Properties).Count -ne $keys.Count -or @($payload.PSObject.Properties.Name | Where-Object {$_ -cnotin $keys}).Count -ne 0){return}
  if($payload.schema -cne 'unified.toolchain-preflight.v1' -or $payload.scope -cne 'COMPONENT_BYTES_ONLY' -or $payload.status -cnotin @('BLOCKED','COMPONENT_BYTES_VERIFIED_ONLY') -or $payload.source_head -cne $UnifiedSourceHead -or $payload.source_tree -cne $UnifiedSourceTree -or $payload.services -cne 'NOT_INSTALLED' -or $payload.native_execution -cne 'NOT_RUN' -or $payload.physical -cne 'NOT_AUTHORIZED'){return}
  foreach($flag in @('installation_closure','execution_authority','trading_authorized','physical_deployment_allowed')){if($payload.$flag -isnot [bool] -or $payload.$flag){return}}
  if($null -eq $payload.integrity){Write-Host '::error title=Raw preflight integrity::status=BLOCKED integrity=UNAVAILABLE';return}
  $integrity=$payload.integrity
  $innerKeys=@('schema','scope','result','artifacts','required_unlocked','all_locked_artifacts_match','installation_closure','publisher_authenticated','execution_authority','native_execution','physical')
  if(@($integrity.PSObject.Properties).Count -ne $innerKeys.Count -or @($integrity.PSObject.Properties.Name | Where-Object {$_ -cnotin $innerKeys}).Count -ne 0 -or $integrity.schema -cne 'unified.windows.toolchain.integrity.v1' -or $integrity.scope -cne 'OFFLINE_BYTE_INTEGRITY_ONLY' -or $integrity.result -cne 'INCOMPLETE' -or $integrity.native_execution -cne 'NOT_RUN' -or $integrity.physical -cne 'NOT_RUN'){return}
  foreach($flag in @('installation_closure','publisher_authenticated','execution_authority')){if($integrity.$flag -isnot [bool] -or $integrity.$flag){return}}
  if($integrity.all_locked_artifacts_match -isnot [bool] -or @($integrity.artifacts).Count -ne 5 -or @($integrity.required_unlocked).Count -ne 2){return}
  $remaining=@{'python-wheels'='NO_REVIEWED_WINDOWS_WHEEL_CLOSURE';'consul'='NO_REVIEWED_OFFICIAL_BINARY_PIN'}
  foreach($item in $integrity.required_unlocked){if(@($item.PSObject.Properties).Count -ne 2 -or $item.component -cnotin @('python-wheels','consul') -or !$remaining.ContainsKey($item.component) -or $item.reason -cne $remaining[$item.component]){return};$remaining.Remove($item.component)}
  $states=@{};$artifactKeys=@('component','version','filename','checksum_basis','status')
  foreach($artifact in $integrity.artifacts){
   if(@($artifact.PSObject.Properties).Count -ne 5 -or @($artifact.PSObject.Properties.Name | Where-Object {$_ -cnotin $artifactKeys}).Count -ne 0 -or $artifact.component -cnotin @('python','node','git','postgresql','nssm') -or $states.ContainsKey($artifact.component) -or $artifact.status -cnotin @('BYTES_MATCH','SIZE_MISMATCH','DIGEST_MISMATCH','MISSING','UNVERIFIED')){return}
   $expected=$metadata[$artifact.component]
   if($artifact.version -cne $expected.version -or $artifact.filename -cne $expected.filename -or $artifact.checksum_basis -cne $expected.provenance.checksum_basis){return}
   $states[$artifact.component]=$artifact.status
  }
  Write-Host ("::error title=Raw preflight integrity::status="+$payload.status)
  foreach($component in @('python','node','git','postgresql','nssm')){Write-Host ("::error title=Raw preflight component::component="+$component+" status="+$states[$component])}
 } catch {
  # An unrecognized/invalid diagnostic never masks the original denial.
 }
}
try {
 $working=Join-Path $target '_smoke';[IO.Directory]::CreateDirectory($working) | Out-Null
 # Both bootstrap executables derive ONLY from the same already verified archive
 # streams. Their byte hashes are not the catalog's compressed archive hashes.
 $phase='EXTRACT_BOOTSTRAP'
 Extract-Component 'python';Extract-Component 'git'
 $python=Executable 'python/tools/python.exe';$git=Executable 'git/cmd/git.exe'
 $cache=Join-Path $working 'preflight-cache';[IO.Directory]::CreateDirectory($cache) | Out-Null
 $arguments=@('-I','-S','-B',$preflight,'--operation','toolchain','--source-root',$UnifiedRoot,'--source-head',$UnifiedSourceHead,'--source-tree',$UnifiedSourceTree,'--source-guard-sha256',$SourceGuardSha256,'--git-executable',$git,'--git-sha256',$inventory['git/cmd/git.exe'].sha256,'--artifact-dir',$ArtifactRoot,'--cache-root',$cache)
 $phase='ROOT_PREFLIGHT'
 $checked=Invoke-PortableProcess $python $inventory['python/tools/python.exe'].sha256 $arguments $working 180
 $proof=$checked.stdout | ConvertFrom-Json
 if($proof.schema -cne 'unified.toolchain-preflight.v1' -or $proof.scope -cne 'COMPONENT_BYTES_ONLY' -or $proof.status -cne 'COMPONENT_BYTES_VERIFIED_ONLY' -or $proof.source_head -cne $UnifiedSourceHead -or $proof.source_tree -cne $UnifiedSourceTree -or $proof.installation_closure -isnot [bool] -or $proof.installation_closure -or $proof.execution_authority -isnot [bool] -or $proof.execution_authority -or $proof.trading_authorized -isnot [bool] -or $proof.trading_authorized -or $proof.physical_deployment_allowed -isnot [bool] -or $proof.physical_deployment_allowed -or $proof.services -cne 'NOT_INSTALLED' -or $proof.physical -cne 'NOT_AUTHORIZED' -or $proof.native_execution -cne 'NOT_RUN'){throw 'PORTABLE_ROOT_PREFLIGHT_CONTRACT'}
 if(@($proof.integrity.artifacts).Count -ne 5 -or @($proof.integrity.artifacts | Where-Object {$_.status -cne 'BYTES_MATCH'}).Count -ne 0 -or $proof.integrity.installation_closure -isnot [bool] -or $proof.integrity.installation_closure -or @($proof.integrity.required_unlocked).Count -ne 2){throw 'PORTABLE_ROOT_GLOBAL_CLOSURE_MUST_REMAIN_BLOCKED'}
 if((Get-PortableHash $catalogPath 65536) -cne $CatalogSha256 -or @(Get-ChildItem -LiteralPath $cache -Force).Count -ne 0){throw 'PORTABLE_CATALOG_OR_CACHE_CHANGED'}
 $phase='EXTRACT_REMAINING'
 foreach($component in @('node','postgresql','nssm')){Extract-Component $component}
 $versions=[ordered]@{}
 $phase='VERSION_PYTHON'
 $versions.python=Version-Tool 'python/tools/python.exe' '^Python 3\.12\.10$' @('-I','-S','-B','--version')
 $phase='VERSION_NODE'
 $versions.node=Version-Tool 'node/node-v22.23.4-win-x64/node.exe' '^v22\.23\.4$' @('--version')
 $phase='VERSION_GIT'
 $versions.git=Version-Tool 'git/cmd/git.exe' '^git version 2\.56\.0\.windows\.4$' @('--version')
 $phase='VERSION_POSTGRESQL'
 $versions.postgresql=Version-Tool 'postgresql/pgsql/bin/postgres.exe' '^postgres \(PostgreSQL\) 18\.6' @('--version')
 $phase='VERSION_NSSM'
 $versions.nssm=Version-Tool 'nssm/nssm-2.24-101-g897c7ad/win64/nssm.exe' '2\.24[.-]101-g897c7ad' @('version')
 $phase='VENV_CREATE_VERIFY'
 $venv=Join-Path $working 'venv'
 $null=Run-Tool 'python/tools/python.exe' @('-I','-S','-B','-m','venv','--copies','--without-pip',$venv) 120
 $venvConfig=Join-Path $venv 'pyvenv.cfg';Assert-PortableLocalPath $venvConfig -MustExist
 if(([IO.File]::ReadAllText($venvConfig)) -notmatch '(?m)^include-system-site-packages = false\s*$'){throw 'PORTABLE_VENV_GLOBAL_SITE_FORBIDDEN'}
 if(@(Get-ChildItem -LiteralPath $venv -Filter '*.pth' -File -Recurse).Count -ne 0){throw 'PORTABLE_VENV_PTH_FORBIDDEN'}
 $venvPython=Join-Path $venv 'Scripts\python.exe';$venvHash=Get-PortableHash $venvPython 134217728
 $allowed=@($inventory.Values | Where-Object {$_.path -match '^python/.*(?:/python\.exe|/venvlauncher\.exe)$'} | ForEach-Object {$_.sha256})
 if($venvHash -cnotin $allowed){throw 'PORTABLE_VENV_EXECUTABLE_ORIGIN'}
 $venvResult=Invoke-PortableProcess $venvPython $venvHash @('-I','-S','-B','--version') $working 20
 if(($venvResult.stdout+' '+$venvResult.stderr).Trim() -cne 'Python 3.12.10'){throw 'PORTABLE_VENV_VERSION'}
 $pgData=Join-Path $working 'pg-data';$pgCtl=Executable 'postgresql/pgsql/bin/pg_ctl.exe';$pgCtlPin=$inventory['postgresql/pgsql/bin/pg_ctl.exe'].sha256
 $phase='POSTGRES_INIT'
 $null=Run-Tool 'postgresql/pgsql/bin/initdb.exe' @('-D',$pgData,'--auth=trust','--username=toolchain_smoke','--no-locale','--encoding=UTF8') 180
 $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0);$listener.Start();$port=$listener.LocalEndpoint.Port;$listener.Stop()
 $log=Join-Path $working 'postgres.log';$pgStarted=$true
 $phase='POSTGRES_START'
 $pgLaunch=Invoke-PortableProcess $pgCtl $pgCtlPin @('-D',$pgData,'-w','-t','45','-l',$log,'-o',(' -c listen_addresses=127.0.0.1 -p '+$port),'start') $working 60 -RetainJob
 $pgJob=$pgLaunch.lease
 $phase='POSTGRES_QUERY'
 $query=Run-Tool 'postgresql/pgsql/bin/psql.exe' @('-h','127.0.0.1','-p',[string]$port,'-U','toolchain_smoke','-d','postgres','-v','ON_ERROR_STOP=1','-At','-c',"SELECT current_setting('data_directory'),current_setting('port'),current_setting('server_version_num')") 20
 $fields=$query.stdout.Trim().Split('|')
 if($fields.Count -ne 3 -or [IO.Path]::GetFullPath($fields[0]) -ine [IO.Path]::GetFullPath($pgData) -or $fields[1] -cne [string]$port -or [int]$fields[2] -lt 180000 -or [int]$fields[2] -ge 190000){throw 'PORTABLE_ISOLATED_POSTGRES_IDENTITY'}
 $phase='POSTGRES_STOP'
 $null=Invoke-PortableProcess $pgCtl $pgCtlPin @('-D',$pgData,'-w','-t','45','stop','-m','fast') $working 60;$pgStarted=$false
 if($null -ne $pgJob){$pgJob.Dispose();$pgJob=$null}
 if([IO.File]::Exists((Join-Path $pgData 'postmaster.pid'))){throw 'PORTABLE_POSTGRES_STOP_UNVERIFIED'}
 $report.result='PASS_COMPONENT_SDK_SMOKE_ONLY';$report.native_execution='EPHEMERAL_COMPONENT_SMOKE_ONLY';$report.versions=$versions
 $report.venv=@{created=$true;system_site_packages=$false;pth_files=0};$report.postgresql=@{isolated_data_verified=$true;loopback_only=$true;stopped=$true;ha='NOT_QUALIFIED'}
 $report.inventory=@($inventory.Values | Sort-Object path)
} catch {
 $failure=$_.Exception;$report.result='BLOCKED';$classification='UNKNOWN';$detail=$_.Exception.ToString()
 foreach($code in @('JOB_DEADLINE','JOB_OUTPUT_LIMIT','JOB_ASSIGN','JOB_PROCESS_FAILED','PROCESS_CREATE_SUSPENDED','PROCESS_RESUME','JOB_CREATE','JOB_LIMIT','ATTRIBUTE_INIT','ATTRIBUTE_HANDLES','PIPE_CREATE','PIPE_FLAGS','PORTABLE_EXPECTED_EXECUTABLE_MISSING','PORTABLE_EXECUTABLE_PIN_MISMATCH','PORTABLE_DERIVED_EXECUTABLE_PIN_MISMATCH','PORTABLE_ARCHIVE_HASH','PORTABLE_ARCHIVE_SIZE','PORTABLE_ZIP_PATH','PORTABLE_ZIP_ALIAS','PORTABLE_ZIP_LINK_OR_TYPE','PORTABLE_ZIP_DIRECTORY_BUDGET','PORTABLE_ZIP_ENTRY_BUDGET','PORTABLE_ZIP_STREAM_BUDGET','PORTABLE_ZIP_STREAM_LENGTH','PORTABLE_PE_REQUIRED','PORTABLE_X64_PE_REQUIRED','PORTABLE_VERSION_MISMATCH','PORTABLE_ROOT_PREFLIGHT_CONTRACT','PORTABLE_ROOT_GLOBAL_CLOSURE_MUST_REMAIN_BLOCKED','PORTABLE_CATALOG_OR_CACHE_CHANGED','PORTABLE_VENV_GLOBAL_SITE_FORBIDDEN','PORTABLE_VENV_PTH_FORBIDDEN','PORTABLE_VENV_EXECUTABLE_ORIGIN','PORTABLE_VENV_VERSION','PORTABLE_ISOLATED_POSTGRES_IDENTITY','PORTABLE_POSTGRES_STOP_UNVERIFIED')){if($detail.Contains($code)){$classification=$code;break}}
 if($phase -ceq 'ROOT_PREFLIGHT'){Write-PrivatePreflightDiagnostic $failure}
 $deadlineNode=$failure
 for($depth=0;$null -ne $deadlineNode -and $depth -lt 8;$depth++){
  if($deadlineNode.Data.Contains('GridPortable.DeadlineState')){
   $state=$deadlineNode.Data['GridPortable.DeadlineState']
   if($state -is [bool[]] -and $state.Length -eq 3){Write-Host "::error title=Owned process deadline state::root_exited=$($state[0]) stdout_done=$($state[1]) stderr_done=$($state[2])"}
   break
  }
  $deadlineNode=$deadlineNode.InnerException
 }
 $kind='UNKNOWN';$node=$failure
 for($depth=0;$null -ne $node -and $depth -lt 8;$depth++){
  $name=$node.GetType().Name
  if($name -cin @('IOException','UnauthorizedAccessException','PathTooLongException','DirectoryNotFoundException','FileNotFoundException','InvalidDataException','ArgumentException','ArgumentNullException','NotSupportedException','OverflowException','MethodException','MethodInvocationException','SetValueInvocationException','GetValueInvocationException','PropertyNotFoundException','PSInvalidCastException','PSArgumentException','InvalidOperationException','RuntimeException')){$kind=$name}
  $node=$node.InnerException
 }
 $file=[IO.Path]::GetFileName($_.InvocationInfo.ScriptName)
 if($file -cnotin @('Stage-PortableWindowsRuntime.ps1','PortableRuntime.psm1')){$file='UNKNOWN'}
 $line=[int]$_.InvocationInfo.ScriptLineNumber
 $report.failure_phase=$phase;$report.failure_code=$classification
 # Host stream keeps this fixed annotation out of the JSON result pipeline.
 Write-Host "::error title=Component SDK phase::phase=$phase code=$classification kind=$kind file=$file line=$line"
}
finally {
 if($pgStarted -and $pgCtl -and $pgData){
  try {$null=Invoke-PortableProcess $pgCtl $pgCtlPin @('-D',$pgData,'-w','-t','45','stop','-m','fast') $working 60;$report.postgresql_cleanup='OWNED_STOP_COMPLETED'}
  catch {$report.postgresql_cleanup='BLOCKED_OWNER_REVIEW_REQUIRED'}
 }
 if($null -ne $pgJob){$pgJob.Dispose();$pgJob=$null}
 # Preserve this owned stage and failure evidence; never recursively delete a
 # possibly active DB, recovery artifact, existing install or unowned namespace.
}
$report | ConvertTo-Json -Depth 14 -Compress
if($null -ne $failure -or $report.result -cne 'PASS_COMPONENT_SDK_SMOKE_ONLY'){throw 'PORTABLE_STAGE_BLOCKED'}
