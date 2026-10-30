#Requires -Version 5.1
# Called in a fresh PS5 compiler process on genuine hosted Windows only.
param([switch]$Probe)
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $env:GITHUB_JOB -cne 's0-windows' -or $env:GITHUB_REPOSITORY -cne 'YehorBabenko88/bybit-cluster-grid' -or [Environment]::MachineName -in @('LS5','PC4')){throw 'HOSTED_BUILD_ONLY'}
$root=$env:S0_NATIVE_BUILD_ROOT
if(!$root -or [IO.Directory]::GetParent($root).FullName -ine $env:S0_LOCAL_APP_DATA_ROOT -or [IO.Path]::GetFileName($root) -cnotmatch '^s0-native-build-[0-9a-f-]{36}$'){throw 'BUILD_NAMESPACE'}
$dll=Join-Path $root 'S0Launcher.dll'
if(!$Probe){
Add-Type -Path @('installer/physical-smoke-s0/S0Launcher.cs','installer/physical-smoke-s0/S0Bootstrap.cs','installer/physical-smoke-s0/TokenObserver.cs','installer/physical-smoke-s0/S0Inputs.cs','installer/physical-smoke-s0/S0Transfer.cs','installer/physical-smoke-s0/S0TransferExport.cs','installer/physical-smoke-s0/S0TransferTransport.cs','installer/physical-smoke-s0/S0UserProfile.cs') -ReferencedAssemblies @('System.dll','System.Core.dll','System.Security.dll','System.IO.Compression.dll') -OutputAssembly $dll -OutputType Library
}
$base=@('installer/physical-smoke-s0-tests/Fixture.cs','installer/physical-smoke-s0-tests/BootstrapTests.cs','installer/physical-smoke-s0-tests/InputTests.cs','installer/physical-smoke-s0-tests/TransferTests.cs','installer/physical-smoke-s0-tests/TransferExportTests.cs','installer/physical-smoke-s0-tests/TransferTransportTests.cs')
if(!$Probe){
Add-Type -Path ($base+@('installer/physical-smoke-s0-tests/UserProfileTests.cs')) -ReferencedAssemblies @($dll,'System.dll','System.Core.dll','System.Security.dll','System.IO.Compression.dll') -OutputAssembly (Join-Path $root 'Fixture.exe') -OutputType ConsoleApplication
Add-Type -Path @('installer/physical-smoke-s0-tests/TokenObserverFixture.cs','installer/physical-smoke-s0-tests/TokenObserverTests.cs') -ReferencedAssemblies @($dll,'System.dll','System.Core.dll','System.Security.dll') -OutputAssembly (Join-Path $root 'TokenObserverFixture.exe') -OutputType ConsoleApplication
}else{
Add-Type -Path ($base+@((Join-Path $root 'ProbeUserProfileTests.cs'),'installer/maintenance/HandoffProbe.cs')) -ReferencedAssemblies @($dll,'System.dll','System.Core.dll','System.Security.dll','System.IO.Compression.dll') -OutputAssembly (Join-Path $root 'HandoffFixture.exe') -OutputType ConsoleApplication
}
