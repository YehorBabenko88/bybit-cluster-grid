# Harmless synthetic ZIP boundary tests. NOT vendor SDK qualification.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or !$env:RUNNER_TEMP -or [Environment]::MachineName.Split('.')[0] -in @('ADMINIT','LS5','PC4')){throw 'HOSTED_WINDOWS_TEST_ONLY'}
Import-Module (Join-Path $PSScriptRoot 'PortableRuntime.psm1') -Force
Add-Type -AssemblyName System.IO.Compression
Assert-PortableLocalPath $env:RUNNER_TEMP -MustExist
$fixtureRoot=Join-Path $env:RUNNER_TEMP ('portable-zip-tests-'+[Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($fixtureRoot) | Out-Null
$passed=0
function Fixture([string[]]$Names,[Nullable[int]]$Attributes=$null) {
 $path=Join-Path $fixtureRoot ([Guid]::NewGuid().ToString('N')+'.zip')
 $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
 try {
  $zip=[IO.Compression.ZipArchive]::new($stream,[IO.Compression.ZipArchiveMode]::Create,$true)
  try {foreach($name in $Names){$entry=$zip.CreateEntry($name);if($null -ne $Attributes){$entry.ExternalAttributes=$Attributes};$output=$entry.Open();try{$output.WriteByte(65)}finally{$output.Dispose()}}}finally{$zip.Dispose()}
 }finally{$stream.Dispose()}
 return $path
}
function Descriptor([string]$Path) {return [pscustomobject]@{component='fixture';max_bytes=1048576;expected_bytes=([IO.FileInfo]$Path).Length;sha256=(Get-PortableHash $Path 1048576)}}
function Reject([string]$Path,[string]$Reason) {
 $opened=$null;$rejected=$false
 try{$opened=Open-PortableArchive $Path (Descriptor $Path)}catch{if($_.Exception.Message -notmatch $Reason){throw};$rejected=$true}finally{if($null -ne $opened){Close-PortableArchive $opened}}
 if(!$rejected){throw 'UNSAFE_ZIP_ACCEPTED'}
 $script:passed++
}
try {
 $good=Fixture @('folder/readme.txt','other.txt','[Content_Types].xml');$opened=Open-PortableArchive $good (Descriptor $good)
 try {
  $destination=Join-Path $fixtureRoot 'expanded';$inventory=Expand-PortableArchive $opened $destination
  if($inventory.Count -ne 3 -or [IO.File]::ReadAllText((Join-Path $destination 'folder\readme.txt')) -cne 'A'){throw 'HONEST_EXTRACTION_FAILED'}
  foreach($file in $inventory){$relative=$file.path.Substring('fixture/'.Length).Replace('/','\');if((Get-PortableHash (Join-Path $destination $relative)) -cne $file.sha256){throw 'DERIVED_HASH_MISMATCH'}}
 }finally{Close-PortableArchive $opened}
 $passed++
 $missingBracket=Join-Path $fixtureRoot '[missing].xml';$missingDenied=$false
 Assert-PortableLocalPath $missingBracket
 try{Assert-PortableLocalPath $missingBracket -MustExist}catch{if($_.Exception.Message -notmatch 'PORTABLE_PATH_MISSING'){throw};$missingDenied=$true}
 if(!$missingDenied -or [IO.File]::Exists($missingBracket)){throw 'MISSING_REQUIRED_PATH_ACCEPTED'};$passed++
 # Actual harmless local junction; observe that no descendant is probed.
 $linkTarget=Join-Path $fixtureRoot 'junction-target';[IO.Directory]::CreateDirectory($linkTarget) | Out-Null
 $sentinel=Join-Path $linkTarget 'sentinel.txt';[IO.File]::WriteAllText($sentinel,'SENTINEL');$sentinelHash=Get-PortableHash $sentinel
 $junction=Join-Path $fixtureRoot 'junction';New-Item -ItemType Junction -Path $junction -Target $linkTarget -ErrorAction Stop | Out-Null
 try {
  $module=Get-Module PortableRuntime
  & $module {
   param([string]$Forbidden)
   $script:PortableTestDescendantProbes=0;$script:PortableTestJunctionProbeSeen=$false
   function Get-Item {
    [CmdletBinding()]param([string]$LiteralPath,[switch]$Force)
    if($LiteralPath -ieq $Forbidden){$script:PortableTestJunctionProbeSeen=$true}
    if($LiteralPath.StartsWith($Forbidden+'\',[StringComparison]::OrdinalIgnoreCase)){$script:PortableTestDescendantProbes++;throw 'DESCENDANT_PROBE_FORBIDDEN'}
    Microsoft.PowerShell.Management\Get-Item -LiteralPath $LiteralPath -Force:$Force -ErrorAction Stop
   }
   try {
    $denied=$false
    try{Assert-PortableLocalPath (Join-Path $Forbidden 'never-created.txt')}catch{if($_.Exception.Message -notmatch 'PORTABLE_REPARSE_FORBIDDEN'){throw};$denied=$true}
    if(!$denied -or !$script:PortableTestJunctionProbeSeen -or $script:PortableTestDescendantProbes -ne 0){throw 'JUNCTION_DESCENDANT_ACCESSED'}
   }finally{Remove-Item -LiteralPath Function:\Get-Item;Remove-Variable PortableTestDescendantProbes,PortableTestJunctionProbeSeen -Scope Script}
  } $junction
  if((Get-PortableHash $sentinel) -cne $sentinelHash){throw 'JUNCTION_TARGET_CHANGED'};$passed++
 }finally{[IO.Directory]::Delete($junction)}
 # A real private Git repository: initial canonical materialization may update
 # index stat metadata; a subsequent real edit MUST remain dirty/rejected.
 $gitFixture=Join-Path $fixtureRoot 'git-fixture';[IO.Directory]::CreateDirectory($gitFixture) | Out-Null
 function Fixture-Git([string[]]$Arguments){$output=@(& git -C $gitFixture @Arguments);if($LASTEXITCODE -ne 0){throw 'PRIVATE_GIT_COMMAND_FAILED'};return $output}
 $null=Fixture-Git @('init','--quiet')
 foreach($setting in @(@('core.autocrlf','false'),@('core.hooksPath','nul'),@('core.attributesFile','nul'),@('core.fsmonitor','false'),@('commit.gpgSign','false'))){$null=Fixture-Git @('config',$setting[0],$setting[1])}
 $gitFile=Join-Path $gitFixture 'fixture.txt';[IO.File]::WriteAllText($gitFile,"FIXTURE`n",[Text.UTF8Encoding]::new($false))
 $null=Fixture-Git @('add','--','fixture.txt');$null=Fixture-Git @('-c','user.name=CI Fixture','-c','user.email=fixture@invalid','commit','--quiet','-m','fixture')
 $fixtureHead=[string](Fixture-Git @('rev-parse','HEAD'));$fixtureTree=[string](Fixture-Git @('rev-parse','HEAD^{tree}'));$fixtureHash=Get-PortableHash $gitFile
 $null=Fixture-Git @('checkout-index','--all','--force','--index')
 if(@(Fixture-Git @('status','--porcelain','--untracked-files=no')).Count -ne 0 -or (Get-PortableHash $gitFile) -cne $fixtureHash){throw 'CANONICAL_GIT_FIXTURE_NOT_CLEAN'}
 [IO.File]::AppendAllText($gitFile,"MUTATION`n",[Text.UTF8Encoding]::new($false))
 if(@(Fixture-Git @('status','--porcelain','--untracked-files=no')).Count -eq 0 -or @(Fixture-Git @('diff','--cached','--name-only','HEAD')).Count -ne 0 -or (Get-PortableHash $gitFile) -ceq $fixtureHash -or [string](Fixture-Git @('rev-parse','HEAD')) -cne $fixtureHead -or [string](Fixture-Git @('rev-parse','HEAD^{tree}')) -cne $fixtureTree){throw 'REAL_GIT_MUTATION_NOT_REJECTED'}
 $passed++
 foreach($name in @('../escape','/absolute','C:/escape','folder/file:ads','folder/CON.txt','folder/trailing.','folder/trailing ','folder\escape','a//b')){Reject (Fixture @($name)) 'PORTABLE_ZIP_(PATH|ALIAS)'}
 Reject (Fixture @('same.txt','SAME.TXT')) 'PORTABLE_ZIP_PATH'
 Reject (Fixture @('a','a/child')) 'PORTABLE_ZIP_FILE_DIRECTORY_COLLISION'
 Reject (Fixture @('link') ([int](0xA000 -shl 16))) 'PORTABLE_ZIP_LINK_OR_TYPE'
 Reject (Fixture @('reparse') 1024) 'PORTABLE_ZIP_LINK_OR_TYPE'
 # Patch only bounded synthetic central-directory metadata, then recompute the
 # fixture descriptor: resource rejection must happen before decompression.
 $budget=Fixture @('small');$bytes=[IO.File]::ReadAllBytes($budget)
 for($i=0;$i -lt $bytes.Length-46;$i++){if([BitConverter]::ToUInt32($bytes,$i) -eq 0x02014b50){[Array]::Copy([BitConverter]::GetBytes([uint32]536870913),0,$bytes,$i+24,4);break}}
 [IO.File]::WriteAllBytes($budget,$bytes);Reject $budget 'PORTABLE_ZIP_ENTRY_BUDGET'
 $count=Fixture @('small');$bytes=[IO.File]::ReadAllBytes($count);$end=$bytes.Length-22
 [Array]::Copy([BitConverter]::GetBytes([uint16]30001),0,$bytes,$end+8,2);[Array]::Copy([BitConverter]::GetBytes([uint16]30001),0,$bytes,$end+10,2)
 [IO.File]::WriteAllBytes($count,$bytes);Reject $count 'PORTABLE_ZIP_DIRECTORY_BUDGET'
 $descriptor=Descriptor $good;$descriptor.sha256='0'*64;$opened=$null;$denied=$false
 try{$opened=Open-PortableArchive $good $descriptor}catch{if($_.Exception.Message -notmatch 'PORTABLE_ARCHIVE_HASH'){throw};$denied=$true}finally{if($null -ne $opened){Close-PortableArchive $opened}}
 if(!$denied){throw 'ARCHIVE_TAMPER_ACCEPTED'};$passed++
 [pscustomobject]@{schema='grid.portable-zip-tests.v1';scope='SYNTHETIC_PATH_RESOURCE_ONLY';passed=$passed;sdk_qualification='NOT_RUN';physical='NOT_RUN'} | ConvertTo-Json -Compress
}finally{
 # Owned synthetic fixtures only; never vendor stages or PostgreSQL data.
 if([IO.Directory]::Exists($fixtureRoot)){Assert-PortableLocalPath $fixtureRoot -MustExist;Remove-Item -LiteralPath $fixtureRoot -Recurse -Force}
}
