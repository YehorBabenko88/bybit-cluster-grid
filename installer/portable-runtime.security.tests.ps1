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
 $good=Fixture @('folder/readme.txt','other.txt');$opened=Open-PortableArchive $good (Descriptor $good)
 try {
  $destination=Join-Path $fixtureRoot 'expanded';$inventory=Expand-PortableArchive $opened $destination
  if($inventory.Count -ne 2 -or [IO.File]::ReadAllText((Join-Path $destination 'folder\readme.txt')) -cne 'A'){throw 'HONEST_EXTRACTION_FAILED'}
  foreach($file in $inventory){$relative=$file.path.Substring('fixture/'.Length).Replace('/','\');if((Get-PortableHash (Join-Path $destination $relative)) -cne $file.sha256){throw 'DERIVED_HASH_MISMATCH'}}
 }finally{Close-PortableArchive $opened}
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
