# Offline SDK primitives. Only the staging entrypoint may authorize SDK execution.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
function Write-PortableMetadataDiagnostic([object]$Item,[string]$Component,[string]$Entry) {
 $kind='OTHER';$count=0
 if($null -eq $Item){$kind='NULL'}elseif($Item -is [array]){$kind='ARRAY';$count=$Item.Count}elseif($Item -is [IO.FileInfo]){$kind='FILE_INFO';$count=1}elseif($Item -is [IO.DirectoryInfo]){$kind='DIR_INFO';$count=1}else{$count=1}
 if($Component -cnotin @('python','node','git','postgresql','nssm')){$Component='UNKNOWN'}
 if(!$Entry -or $Entry.Length -gt 512 -or $Entry -match '[^ -~]' -or $Entry.StartsWith('/') -or $Entry.Contains('\') -or $Entry.Contains(':') -or @($Entry.Split('/') | Where-Object {$_ -in @('.','..')}).Count -ne 0){$Entry='UNKNOWN'}
 $commandKind='OTHER'
 try{$command=Get-Command Get-Item -CommandType Cmdlet,Function,Alias -ErrorAction Stop | Select-Object -First 1;if([string]$command.CommandType -cin @('Cmdlet','Function','Alias')){$commandKind=[string]$command.CommandType}}catch{}
 Write-Host ("::error title=Local metadata boundary::component="+$Component+" entry="+$Entry.Replace('%','%25')+" type="+$kind+" count="+$count+" command="+$commandKind)
}
function Assert-PortableLocalPath([string]$Path,[switch]$MustExist,[string]$PublicComponent='UNKNOWN',[string]$PublicEntry='UNKNOWN') {
 if ($Path -notmatch '^[A-Za-z]:\\' -or $Path.Contains('/') -or $Path.Substring(2).Contains(':') -or $Path.Contains('..')) {throw 'PORTABLE_LOCAL_NAMESPACE_REQUIRED'}
 $full=[IO.Path]::GetFullPath($Path);$anchor=[IO.Path]::GetPathRoot($full)
 if ([IO.DriveInfo]::new($anchor).DriveType -ne [IO.DriveType]::Fixed) {throw 'PORTABLE_FIXED_DRIVE_REQUIRED'}
 $drive=Get-PSDrive -Name ($anchor.Substring(0,1)) -ErrorAction Stop
 if ($drive.Provider.Name -cne 'FileSystem' -or $drive.Root.TrimEnd('\') -ine $anchor.TrimEnd('\')) {throw 'PORTABLE_DRIVE_NAMESPACE_MISMATCH'}
 $parts=New-Object 'System.Collections.Generic.List[string]';$cursor=$full
 while($cursor){$parts.Add($cursor);$next=[IO.Path]::GetDirectoryName($cursor.TrimEnd('\'));if($next -eq $cursor){break};$cursor=$next}
 for($i=$parts.Count-1;$i -ge 0;$i--){
  $item=$null
  try {$item=Get-Item -LiteralPath $parts[$i] -Force -ErrorAction Stop}
  catch [Management.Automation.ItemNotFoundException] {if($MustExist){throw 'PORTABLE_PATH_MISSING'};return}
  if($null -eq $item){
   # WinPS can return no object for a missing literal bracket filename. Never
   # treat NULL as valid metadata: confirm absence via the OS after parents
   # were checked, then apply exactly the existing missing-path policy.
   try{[void][IO.File]::GetAttributes($parts[$i])}
   catch [IO.FileNotFoundException]{if($MustExist){throw 'PORTABLE_PATH_MISSING'};return}
   catch [IO.DirectoryNotFoundException]{if($MustExist){throw 'PORTABLE_PATH_MISSING'};return}
  }
  if($null -eq $item -or ($item -isnot [IO.FileInfo] -and $item -isnot [IO.DirectoryInfo]) -or $null -eq $item.PSObject.Properties['Attributes']){Write-PortableMetadataDiagnostic $item $PublicComponent $PublicEntry;throw 'PORTABLE_PATH_METADATA_UNAVAILABLE'}
  try{$attributes=$item.Attributes}catch{Write-PortableMetadataDiagnostic $item $PublicComponent $PublicEntry;throw}
  if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw 'PORTABLE_REPARSE_FORBIDDEN'}
  if($i -ne 0 -and !$item.PSIsContainer){throw 'PORTABLE_ANCESTOR_NOT_DIRECTORY'}
 }
}
function Get-PortableHash([string]$Path,[long]$Maximum=1073741824,[object]$ExpectedBytes=$null) {
 Assert-PortableLocalPath $Path -MustExist
 $stream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 try {
  if($stream.Length -lt 1 -or $stream.Length -gt $Maximum -or ($null -ne $ExpectedBytes -and $stream.Length -ne $ExpectedBytes)){throw 'PORTABLE_ARTIFACT_SIZE'}
  $sha=[Security.Cryptography.SHA256]::Create()
  try {return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','').ToLowerInvariant()} finally {$sha.Dispose()}
 } finally {$stream.Dispose()}
}
function Read-PortableCatalog([string]$Path,[string]$ExpectedSha256) {
 if($ExpectedSha256 -cnotmatch '^[a-f0-9]{64}$'){throw 'PORTABLE_EXTERNAL_CATALOG_PIN_REQUIRED'}
 Assert-PortableLocalPath $Path -MustExist
 $stream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 try {
  if($stream.Length -lt 2 -or $stream.Length -gt 65536){throw 'PORTABLE_CATALOG_SIZE'}
  $sha=[Security.Cryptography.SHA256]::Create()
  try {$hash=([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','').ToLowerInvariant()} finally {$sha.Dispose()}
  if($hash -cne $ExpectedSha256){throw 'PORTABLE_CATALOG_PIN_MISMATCH'}
  $stream.Position=0;$bytes=New-Object byte[] ([int]$stream.Length)
  $read=0;while($read -lt $bytes.Length){$n=$stream.Read($bytes,$read,$bytes.Length-$read);if($n -le 0){throw 'PORTABLE_CATALOG_TRUNCATED'};$read+=$n}
  # Exact externally reviewed bytes are the bootstrap trust anchor; this is
  # data-only shape checking, not a replacement for Root's catalog validator.
  $catalog=([Text.UTF8Encoding]::new($false,$true)).GetString($bytes) | ConvertFrom-Json
 } finally {$stream.Dispose()}
 if($catalog.schema -cne 'unified.windows.toolchain.catalog.v1' -or $catalog.platform -cne 'windows-x64' -or $catalog.scope -cne 'OFFLINE_BYTE_INTEGRITY_ONLY' -or @($catalog.artifacts).Count -ne 5){throw 'PORTABLE_CATALOG_CONTRACT'}
 $seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
 foreach($artifact in $catalog.artifacts){
  if($artifact.component -cnotin @('python','node','git','postgresql','nssm') -or !$seen.Add($artifact.component) -or $artifact.filename -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$' -or $artifact.sha256 -cnotmatch '^[a-f0-9]{64}$'){throw 'PORTABLE_CATALOG_ARTIFACT'}
  if(($artifact.max_bytes -isnot [int] -and $artifact.max_bytes -isnot [long]) -or $artifact.max_bytes -lt 1 -or $artifact.max_bytes -gt 1073741824){throw 'PORTABLE_CATALOG_BUDGET'}
  if($null -ne $artifact.expected_bytes -and (($artifact.expected_bytes -isnot [int] -and $artifact.expected_bytes -isnot [long]) -or $artifact.expected_bytes -lt 1 -or $artifact.expected_bytes -gt $artifact.max_bytes)){throw 'PORTABLE_CATALOG_EXPECTED_SIZE'}
 }
 if(@($catalog.required_unlocked).Count -ne 2){throw 'PORTABLE_GLOBAL_CLOSURE_UNRESOLVED'}
 return $catalog
}
function Read-PortableBytes([IO.Stream]$Stream,[int]$Count) {
 $bytes=New-Object byte[] $Count;$offset=0
 while($offset -lt $Count){$n=$Stream.Read($bytes,$offset,$Count-$offset);if($n -le 0){throw 'PORTABLE_ZIP_TRUNCATED'};$offset+=$n}
 return ,$bytes
}
function Read-PortableZipDirectory([IO.Stream]$Stream) {
 # Bound central-directory allocation BEFORE ZipArchive materializes entries.
 if($Stream.Length -lt 22){throw 'PORTABLE_ZIP_FORMAT'}
 $tailLength=[int][Math]::Min(65557,$Stream.Length);$Stream.Position=$Stream.Length-$tailLength
 $tail=Read-PortableBytes $Stream $tailLength;$end=-1
 for($i=$tail.Length-22;$i -ge 0;$i--){if([BitConverter]::ToUInt32($tail,$i) -eq 0x06054b50 -and $i+22+[BitConverter]::ToUInt16($tail,$i+20) -eq $tail.Length){$end=$i;break}}
 if($end -lt 0){throw 'PORTABLE_ZIP_END'}
 $count=[int][BitConverter]::ToUInt16($tail,$end+10);$size=[long][BitConverter]::ToUInt32($tail,$end+12);$start=[long][BitConverter]::ToUInt32($tail,$end+16)
 if([BitConverter]::ToUInt16($tail,$end+4) -ne 0 -or [BitConverter]::ToUInt16($tail,$end+6) -ne 0 -or [BitConverter]::ToUInt16($tail,$end+8) -ne $count -or $count -lt 1 -or $count -gt 30000 -or $size -gt 16777216 -or $start+$size -gt $Stream.Length-$tailLength+$end){throw 'PORTABLE_ZIP_DIRECTORY_BUDGET'}
 $Stream.Position=$start;$central=Read-PortableBytes $Stream ([int]$size)
 $records=New-Object 'System.Collections.Generic.List[object]';$names=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
 $kinds=[Collections.Generic.Dictionary[string,bool]]::new([StringComparer]::OrdinalIgnoreCase)
 $offset=0;[long]$expanded=0
 for($i=0;$i -lt $count;$i++){
  if($offset+46 -gt $central.Length -or [BitConverter]::ToUInt32($central,$offset) -ne 0x02014b50){throw 'PORTABLE_ZIP_CENTRAL'}
  $flags=[int][BitConverter]::ToUInt16($central,$offset+8);$method=[int][BitConverter]::ToUInt16($central,$offset+10)
  $compressed=[long][BitConverter]::ToUInt32($central,$offset+20);$length=[long][BitConverter]::ToUInt32($central,$offset+24)
  $nameLength=[int][BitConverter]::ToUInt16($central,$offset+28);$extra=[int][BitConverter]::ToUInt16($central,$offset+30);$comment=[int][BitConverter]::ToUInt16($central,$offset+32)
  $attributes=[long][BitConverter]::ToUInt32($central,$offset+38);$local=[long][BitConverter]::ToUInt32($central,$offset+42)
  if(($flags -band 65) -ne 0 -or $method -notin @(0,8) -or $nameLength -lt 1 -or $nameLength -gt 512 -or $extra -gt 4096 -or $comment -gt 4096 -or [BitConverter]::ToUInt16($central,$offset+34) -ne 0 -or $length -gt 536870912 -or $local+30 -gt $start -or $compressed -gt $Stream.Length -or $offset+46+$nameLength+$extra+$comment -gt $central.Length){throw 'PORTABLE_ZIP_ENTRY_BUDGET'}
  $nameBytes=New-Object byte[] $nameLength;[Array]::Copy($central,$offset+46,$nameBytes,0,$nameLength)
  if(@($nameBytes | Where-Object {$_ -lt 32 -or $_ -gt 126}).Count -ne 0){throw 'PORTABLE_ZIP_ASCII_NAMESPACE_REQUIRED'}
  $name=[Text.Encoding]::ASCII.GetString($nameBytes);$directory=$name.EndsWith('/');$relative=$name.TrimEnd('/')
  if(!$relative -or $name.StartsWith('/') -or $name.Contains('\') -or $name -match '[<>:"|?*]' -or !$names.Add($relative)){throw 'PORTABLE_ZIP_PATH'}
  $parts=$relative.Split('/');$prefix=''
  for($p=0;$p -lt $parts.Length;$p++){
   $part=$parts[$p]
   if(!$part -or $part -in @('.','..') -or $part.EndsWith('.') -or $part.EndsWith(' ') -or $part.Split('.')[0] -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$'){throw 'PORTABLE_ZIP_ALIAS'}
   $prefix=if($prefix){$prefix+'/'+$part}else{$part};$isDirectory=($p -lt $parts.Length-1 -or $directory)
   if($kinds.ContainsKey($prefix)) {if(!$kinds[$prefix] -or !$isDirectory){throw 'PORTABLE_ZIP_FILE_DIRECTORY_COLLISION'}} else {$kinds.Add($prefix,$isDirectory)}
  }
  $unix=($attributes -shr 16) -band 61440
  if($unix -notin @(0,16384,32768) -or ($attributes -band 1024) -ne 0 -or ($directory -and ($length -ne 0 -or $compressed -gt 32 -or $unix -eq 32768)) -or (!$directory -and ($unix -eq 16384 -or ($attributes -band 16) -ne 0))){throw 'PORTABLE_ZIP_LINK_OR_TYPE'}
  $Stream.Position=$local;$header=Read-PortableBytes $Stream 30
  if([BitConverter]::ToUInt32($header,0) -ne 0x04034b50 -or [BitConverter]::ToUInt16($header,6) -ne $flags -or [BitConverter]::ToUInt16($header,8) -ne $method){throw 'PORTABLE_ZIP_LOCAL_HEADER'}
  $localName=[int][BitConverter]::ToUInt16($header,26);$localExtra=[int][BitConverter]::ToUInt16($header,28)
  if($localName -ne $nameLength -or $localExtra -gt 4096 -or $local+30+$localName+$localExtra+$compressed -gt $start){throw 'PORTABLE_ZIP_LOCAL_BUDGET'}
  $actualName=Read-PortableBytes $Stream $localName
  if([Convert]::ToBase64String($actualName) -cne [Convert]::ToBase64String($nameBytes)){throw 'PORTABLE_ZIP_NAME_MISMATCH'}
  $expanded+=$length;if($expanded -gt 4294967296){throw 'PORTABLE_ZIP_EXPANDED_BUDGET'}
  $records.Add([pscustomobject]@{name=$name;relative=$relative;directory=$directory;length=$length;compressed=$compressed})
  $offset+=46+$nameLength+$extra+$comment
 }
 if($offset -ne $central.Length){throw 'PORTABLE_ZIP_TRAILING_DIRECTORY'}
 return [pscustomobject]@{records=$records;expanded_bytes=$expanded}
}
function Open-PortableArchive([string]$Path,[object]$Descriptor) {
 Assert-PortableLocalPath $Path -MustExist
 $stream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 $archive=$null
 try {
  if($stream.Length -lt 1 -or $stream.Length -gt $Descriptor.max_bytes -or ($null -ne $Descriptor.expected_bytes -and $stream.Length -ne $Descriptor.expected_bytes)){throw 'PORTABLE_ARCHIVE_SIZE'}
  $sha=[Security.Cryptography.SHA256]::Create()
  try {$actual=([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','').ToLowerInvariant()} finally {$sha.Dispose()}
  if($actual -cne $Descriptor.sha256){throw 'PORTABLE_ARCHIVE_HASH'}
  $metadata=Read-PortableZipDirectory $stream
  $stream.Position=0
  $archive=[IO.Compression.ZipArchive]::new($stream,[IO.Compression.ZipArchiveMode]::Read,$true)
  if($archive.Entries.Count -ne $metadata.records.Count){throw 'PORTABLE_ZIP_ENTRY_COUNT'}
  for($i=0;$i -lt $archive.Entries.Count;$i++){
   $entry=$archive.Entries[$i];$record=$metadata.records[$i]
   if($entry.FullName -cne $record.name -or $entry.Length -ne $record.length -or $entry.CompressedLength -ne $record.compressed){throw 'PORTABLE_ZIP_METADATA_MISMATCH'}
  }
  return [pscustomobject]@{stream=$stream;archive=$archive;metadata=$metadata;descriptor=$Descriptor}
 } catch {if($null -ne $archive){$archive.Dispose()};$stream.Dispose();throw}
}
function Close-PortableArchive([object]$Archive) {$Archive.archive.Dispose();$Archive.stream.Dispose()}
function Expand-PortableArchive([object]$Archive,[string]$Destination) {
 Assert-PortableLocalPath $Destination
 if([IO.Directory]::Exists($Destination) -or [IO.File]::Exists($Destination)){throw 'PORTABLE_NEW_COMPONENT_ROOT_REQUIRED'}
 [IO.Directory]::CreateDirectory($Destination) | Out-Null
 $inventory=New-Object 'System.Collections.Generic.List[object]';$buffer=New-Object byte[] 1048576
 for($i=0;$i -lt $Archive.metadata.records.Count;$i++){
  $record=$Archive.metadata.records[$i];$entry=$Archive.archive.Entries[$i]
  $path=Join-Path $Destination ($record.relative.Replace('/','\'));Assert-PortableLocalPath $path -PublicComponent $Archive.descriptor.component -PublicEntry $record.relative
  if($record.directory){[IO.Directory]::CreateDirectory($path) | Out-Null;continue}
  [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path)) | Out-Null
  $inputStream=$null;$outputStream=$null;$sha=$null;[long]$total=0
  try {
   $inputStream=$entry.Open();$outputStream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);$sha=[Security.Cryptography.SHA256]::Create()
   while(($n=$inputStream.Read($buffer,0,$buffer.Length)) -gt 0){$total+=$n;if($total -gt $record.length){throw 'PORTABLE_ZIP_STREAM_BUDGET'};$outputStream.Write($buffer,0,$n);$null=$sha.TransformBlock($buffer,0,$n,$buffer,0)}
   if($total -ne $record.length){throw 'PORTABLE_ZIP_STREAM_LENGTH'}
   $null=$sha.TransformFinalBlock([byte[]]@(),0,0)
   $inventory.Add([pscustomobject]@{path=$Archive.descriptor.component+'/'+$record.relative;bytes=$total;sha256=([BitConverter]::ToString($sha.Hash)).Replace('-','').ToLowerInvariant()})
  } finally {if($null -ne $sha){$sha.Dispose()};if($null -ne $inputStream){$inputStream.Dispose()};if($null -ne $outputStream){$outputStream.Dispose()}}
 }
 return ,$inventory
}
function ConvertTo-PortableArgument([string]$Value) {
 if($Value.Contains([char]0) -or $Value.Contains("`r") -or $Value.Contains("`n")){throw 'PORTABLE_ARGUMENT_REJECTED'}
 $escaped=[regex]::Replace($Value,'(\\*)"','$1$1\"');$escaped=[regex]::Replace($escaped,'(\\+)$','$1$1')
 return '"'+$escaped+'"'
}
$script:PortableJobLoaded=$false
function Initialize-PortableJob([string]$Source,[string]$ExpectedSha256) {
 if($script:PortableJobLoaded){throw 'PORTABLE_JOB_ALREADY_INITIALIZED'}
 if($ExpectedSha256 -cnotmatch '^[a-f0-9]{64}$'){throw 'PORTABLE_JOB_PIN_REQUIRED'}
 Assert-PortableLocalPath $Source -MustExist
 $stream=[IO.File]::Open($Source,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 try {
  if($stream.Length -lt 1 -or $stream.Length -gt 65536){throw 'PORTABLE_JOB_SOURCE_SIZE'}
  $raw=Read-PortableBytes $stream ([int]$stream.Length);$sha=[Security.Cryptography.SHA256]::Create()
  try{$actual=([BitConverter]::ToString($sha.ComputeHash($raw))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
  if($actual -cne $ExpectedSha256){throw 'PORTABLE_JOB_SOURCE_PIN_MISMATCH'}
 }finally{$stream.Dispose()}
 # This function is called only AFTER the hosted ephemeral gate. Neither module
 # import nor Prepare invokes the compiler or emits a native helper assembly.
 if('GridPortable.JobProcess' -as [type]){throw 'PORTABLE_JOB_AMBIENT_TYPE_FORBIDDEN'}
 Add-Type -TypeDefinition ([Text.UTF8Encoding]::new($false,$true).GetString($raw)) -Language CSharp
 $script:PortableJobLoaded=$true
}
function Invoke-PortableProcess([string]$Executable,[string]$ExpectedSha256,[string[]]$Arguments,[string]$WorkingDirectory,[int]$TimeoutSeconds=30,[switch]$RetainJob) {
 if((Get-PortableHash $Executable 134217728) -cne $ExpectedSha256){throw 'PORTABLE_EXECUTABLE_PIN_MISMATCH'}
 Assert-PortableLocalPath $WorkingDirectory -MustExist
 $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$Executable;$start.Arguments=($Arguments | ForEach-Object {ConvertTo-PortableArgument $_}) -join ' '
 $start.WorkingDirectory=$WorkingDirectory;$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
 # Private child environment only. Never edit global PATH or registry settings.
 $start.EnvironmentVariables.Clear()
 $windows=[Environment]::GetFolderPath([Environment+SpecialFolder]::Windows);Assert-PortableLocalPath $windows -MustExist
 $start.EnvironmentVariables['SystemRoot']=$windows;$start.EnvironmentVariables['WINDIR']=$windows
 foreach($name in @('TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA')) {$start.EnvironmentVariables[$name]=$WorkingDirectory}
 $start.EnvironmentVariables['PGPASSFILE']=Join-Path $WorkingDirectory 'nonexistent-pgpass'
 $start.EnvironmentVariables['PGSERVICEFILE']=Join-Path $WorkingDirectory 'nonexistent-pgservice'
 $start.EnvironmentVariables['PATH']=[IO.Path]::GetDirectoryName($Executable)+';'+(Join-Path $windows 'System32')
 $start.EnvironmentVariables['PYTHONDONTWRITEBYTECODE']='1';$start.EnvironmentVariables['GIT_CONFIG_NOSYSTEM']='1';$start.EnvironmentVariables['GIT_CONFIG_GLOBAL']='NUL';$start.EnvironmentVariables['GIT_CONFIG_SYSTEM']='NUL';$start.EnvironmentVariables['GIT_TERMINAL_PROMPT']='0';$start.EnvironmentVariables['GIT_NO_LAZY_FETCH']='1'
 if($TimeoutSeconds -lt 1 -or $TimeoutSeconds -gt 180){throw 'PORTABLE_PROCESS_TIMEOUT_BUDGET'}
 if(!$script:PortableJobLoaded){throw 'PORTABLE_JOB_NOT_INITIALIZED'}
 $environment=[Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
 foreach($key in $start.EnvironmentVariables.Keys){$environment.Add([string]$key,[string]$start.EnvironmentVariables[$key])}
 $result=[GridPortable.JobProcess]::Run($Executable,$start.Arguments,$WorkingDirectory,$environment,$TimeoutSeconds,[bool]$RetainJob)
 return [pscustomobject]@{stdout=$result.Stdout;stderr=$result.Stderr;exit_code=$result.ExitCode;lease=$result}

}
Export-ModuleMember -Function Assert-PortableLocalPath,Get-PortableHash,Read-PortableCatalog,Open-PortableArchive,Close-PortableArchive,Expand-PortableArchive,Initialize-PortableJob,Invoke-PortableProcess
