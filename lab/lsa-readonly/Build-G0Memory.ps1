param([Parameter(Mandatory=$true)][string]$Output,[switch]$Tests)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if([Environment]::MachineName -ieq 'PC4'){throw 'PC4_BUILD_OR_TEST_EXECUTION_FORBIDDEN'}
if($PSVersionTable.PSVersion.Major -ne 5 -or -not [Environment]::Is64BitProcess){throw 'BUILD_REQUIRES_PS51_X64'}
if([IO.File]::Exists($Output)){throw 'BUILD_OUTPUT_EXISTS'}
$files=@('LsaRights.cs','SidBoundReader.cs');if($Tests){$files+=@('MockTests.cs','G0MockTests.cs')}
$source=@();foreach($f in $files){$source+=[IO.File]::ReadAllText((Join-Path $PSScriptRoot $f))}
# Offline/hosted build only. Never invoke this compiler on PC4.
Add-Type -TypeDefinition ($source -join "`n") -OutputAssembly $Output -OutputType Library -ErrorAction Stop
