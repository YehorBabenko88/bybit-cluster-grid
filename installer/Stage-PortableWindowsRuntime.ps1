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
$inventory=@{};$pgStarted=$false;$pgData=$null;$pgCtl=$null;$pgCtlPin=$null;$working=$null;$failure=$null
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
try {
 $working=Join-Path $target '_smoke';[IO.Directory]::CreateDirectory($working) | Out-Null
 # Both bootstrap executables derive ONLY from the same already verified archive
 # streams. Their byte hashes are not the catalog's compressed archive hashes.
 Extract-Component 'python';Extract-Component 'git'
 $python=Executable 'python/tools/python.exe';$git=Executable 'git/cmd/git.exe'
 $cache=Join-Path $working 'preflight-cache';[IO.Directory]::CreateDirectory($cache) | Out-Null
 $arguments=@('-I','-S','-B',$preflight,'--operation','toolchain','--source-root',$UnifiedRoot,'--source-head',$UnifiedSourceHead,'--source-tree',$UnifiedSourceTree,'--source-guard-sha256',$SourceGuardSha256,'--git-executable',$git,'--git-sha256',$inventory['git/cmd/git.exe'].sha256,'--artifact-dir',$ArtifactRoot,'--cache-root',$cache)
 $checked=Invoke-PortableProcess $python $inventory['python/tools/python.exe'].sha256 $arguments $working 180
 $proof=$checked.stdout | ConvertFrom-Json
 if($proof.schema -cne 'unified.toolchain-preflight.v1' -or $proof.scope -cne 'COMPONENT_BYTES_ONLY' -or $proof.status -cne 'COMPONENT_BYTES_VERIFIED_ONLY' -or $proof.source_head -cne $UnifiedSourceHead -or $proof.source_tree -cne $UnifiedSourceTree -or $proof.installation_closure -isnot [bool] -or $proof.installation_closure -or $proof.execution_authority -isnot [bool] -or $proof.execution_authority -or $proof.trading_authorized -isnot [bool] -or $proof.trading_authorized -or $proof.physical_deployment_allowed -isnot [bool] -or $proof.physical_deployment_allowed -or $proof.services -cne 'NOT_INSTALLED' -or $proof.physical -cne 'NOT_AUTHORIZED' -or $proof.native_execution -cne 'NOT_RUN'){throw 'PORTABLE_ROOT_PREFLIGHT_CONTRACT'}
 if(@($proof.integrity.artifacts).Count -ne 5 -or @($proof.integrity.artifacts | Where-Object {$_.status -cne 'BYTES_MATCH'}).Count -ne 0 -or $proof.integrity.installation_closure -isnot [bool] -or $proof.integrity.installation_closure -or @($proof.integrity.required_unlocked).Count -ne 2){throw 'PORTABLE_ROOT_GLOBAL_CLOSURE_MUST_REMAIN_BLOCKED'}
 if((Get-PortableHash $catalogPath 65536) -cne $CatalogSha256 -or @(Get-ChildItem -LiteralPath $cache -Force).Count -ne 0){throw 'PORTABLE_CATALOG_OR_CACHE_CHANGED'}
 foreach($component in @('node','postgresql','nssm')){Extract-Component $component}
 $versions=[ordered]@{}
 $versions.python=Version-Tool 'python/tools/python.exe' '^Python 3\.12\.10$' @('-I','-S','-B','--version')
 $versions.node=Version-Tool 'node/node-v22.23.4-win-x64/node.exe' '^v22\.23\.4$' @('--version')
 $versions.git=Version-Tool 'git/cmd/git.exe' '^git version 2\.56\.0\.windows\.4$' @('--version')
 $versions.postgresql=Version-Tool 'postgresql/pgsql/bin/postgres.exe' '^postgres \(PostgreSQL\) 18\.6' @('--version')
 $versions.nssm=Version-Tool 'nssm/nssm-2.24-101-g897c7ad/win64/nssm.exe' '2\.24[.-]101-g897c7ad' @('version')
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
 $null=Run-Tool 'postgresql/pgsql/bin/initdb.exe' @('-D',$pgData,'--auth=trust','--username=toolchain_smoke','--no-locale','--encoding=UTF8') 180
 $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0);$listener.Start();$port=$listener.LocalEndpoint.Port;$listener.Stop()
 $log=Join-Path $working 'postgres.log';$pgStarted=$true
 $pgLaunch=Invoke-PortableProcess $pgCtl $pgCtlPin @('-D',$pgData,'-w','-t','45','-l',$log,'-o',(' -c listen_addresses=127.0.0.1 -p '+$port),'start') $working 60 -RetainJob
 $pgJob=$pgLaunch.lease
 $query=Run-Tool 'postgresql/pgsql/bin/psql.exe' @('-h','127.0.0.1','-p',[string]$port,'-U','toolchain_smoke','-d','postgres','-v','ON_ERROR_STOP=1','-At','-c',"SELECT current_setting('data_directory'),current_setting('port'),current_setting('server_version_num')") 20
 $fields=$query.stdout.Trim().Split('|')
 if($fields.Count -ne 3 -or [IO.Path]::GetFullPath($fields[0]) -ine [IO.Path]::GetFullPath($pgData) -or $fields[1] -cne [string]$port -or [int]$fields[2] -lt 180000 -or [int]$fields[2] -ge 190000){throw 'PORTABLE_ISOLATED_POSTGRES_IDENTITY'}
 $null=Invoke-PortableProcess $pgCtl $pgCtlPin @('-D',$pgData,'-w','-t','45','stop','-m','fast') $working 60;$pgStarted=$false
 if($null -ne $pgJob){$pgJob.Dispose();$pgJob=$null}
 if([IO.File]::Exists((Join-Path $pgData 'postmaster.pid'))){throw 'PORTABLE_POSTGRES_STOP_UNVERIFIED'}
 $report.result='PASS_COMPONENT_SDK_SMOKE_ONLY';$report.native_execution='EPHEMERAL_COMPONENT_SMOKE_ONLY';$report.versions=$versions
 $report.venv=@{created=$true;system_site_packages=$false;pth_files=0};$report.postgresql=@{isolated_data_verified=$true;loopback_only=$true;stopped=$true;ha='NOT_QUALIFIED'}
 $report.inventory=@($inventory.Values | Sort-Object path)
} catch {$failure=$_.Exception;$report.result='BLOCKED'}
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
