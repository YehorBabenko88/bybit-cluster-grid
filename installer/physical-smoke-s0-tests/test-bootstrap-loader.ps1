# Genuine hosted disposable Medium shell only. This driver performs read-only Plan.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$Head,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$Sha,
    [Parameter(Mandatory=$true)][string]$Sid,
    [Parameter(Mandatory=$true)][string]$Target,
    [Parameter(Mandatory=$true)][string]$Loader
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not [Environment]::Is64BitProcess -or
    $env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:GITHUB_REPOSITORY -cne 'YehorBabenko88/bybit-cluster-grid' -or $env:GITHUB_JOB -cne 's0-windows' -or
    [Environment]::MachineName -ieq 'LS5' -or [Environment]::MachineName -ieq 'PC4' -or
    $Head -cne $env:EXACT_HEAD_SHA) { throw 'FIXTURE_LOADER_HOSTED_REQUIRED' }
$shellMajor = [int]$PSVersionTable.PSVersion.Major
if ($shellMajor -ne 5 -and $shellMajor -ne 7) { throw 'FIXTURE_LOADER_SHELL' }
foreach ($path in @($Root,$Target,$Loader)) {
    if (-not [IO.Path]::IsPathRooted($path) -or $path.StartsWith('\\',[StringComparison]::Ordinal) -or
        $path.IndexOf([char]0) -ge 0 -or $path.IndexOf([char]10) -ge 0 -or $path.IndexOf([char]13) -ge 0) {
        throw 'FIXTURE_LOADER_PATH'
    }
}
$rootPath = [IO.Path]::GetFullPath($Root).TrimEnd([char]92)
$targetPath = [IO.Path]::GetFullPath($Target)
$loaderPath = [IO.Path]::GetFullPath($Loader)
$expectedLoader = [IO.Path]::Combine($rootPath,'installer','physical-smoke-s0-bootstrap.ps1')
$sourceZip = [IO.Path]::Combine($rootPath,'source.zip')
# The parent holds custody of these exact package files throughout this child.
if ($loaderPath -ine $expectedLoader -or -not [IO.File]::Exists($loaderPath) -or
    -not [IO.File]::Exists($sourceZip) -or [IO.File]::Exists($targetPath) -or [IO.Directory]::Exists($targetPath)) {
    throw 'FIXTURE_LOADER_INPUT'
}
if ('GridS0.Bootstrap' -as [type]) { throw 'FIXTURE_LOADER_FRESH_SHELL_REQUIRED' }
$plans = @(& $loaderPath -Action Plan -SourceZip $sourceZip -ExpectedSha256 $Sha -ExpectedHead $Head -ExpectedSid $Sid -TargetRoot $targetPath)
if ($plans.Count -ne 1 -or $plans[0].GetType().FullName -cne 'GridS0.BootstrapReceipt') { throw 'FIXTURE_LOADER_RECEIPT' }
$plan = $plans[0]
if ($plan.Status -cne 'PLAN_ONLY' -or $plan.Head -cne $Head -or $plan.Sha256 -cne $Sha -or
    $plan.S0Execute -isnot [bool] -or $plan.S0Execute -ne $false -or
    $plan.G1Execute -isnot [bool] -or $plan.G1Execute -ne $false -or
    $plan.Cleanup -isnot [bool] -or $plan.Cleanup -ne $false -or $null -ne $plan.RootIdentity -or
    [IO.File]::Exists($targetPath) -or [IO.Directory]::Exists($targetPath)) { throw 'FIXTURE_LOADER_PLAN_ONLY' }
$facts = [GridS0.TokenObserver]::RequireStandard($Sid)
if (-not $facts.Standard -or $facts.Sid -cne $Sid -or $facts.Integrity -cne 'S-1-16-8192' -or $facts.Elevated) {
    throw 'FIXTURE_LOADER_STANDARD_PRIMARY'
}
# No raw host SID, groups, privileges, path or token identifiers leave this shell.
[ordered]@{
    head=$Head
    scope='HOSTED_LOADER_NOT_PHYSICAL'
    loader_plan_only=$true
    shell_major=$shellMajor
    s0_execute=$false
    g1_execute=$false
    cleanup=$false
    root_absent=$true
    standard_primary=$true
} | ConvertTo-Json -Compress
