#Requires -Version 5.1
<#
.SYNOPSIS
Discover and stage a successful main-branch GitHub Actions release.
.DESCRIPTION
Never activates, stops tasks, changes current.version, or deletes releases.
Requires authenticated GitHub CLI. Checks BOTH preflight and windows-bundle
for the same exact main commit, verifies artifact checksum and embedded manifest.
#>
[CmdletBinding()]
param(
    [string]$Repository = 'YehorBabenko88/bybit-cluster-grid',
    [string]$StageRoot = "$env:ProgramData\BybitClusterGrid\update-staging",
    [switch]$Download
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($Repository -ne 'YehorBabenko88/bybit-cluster-grid') {
    throw 'Repository is pinned; refusing untrusted source'
}
$gh = Get-Command gh.exe -ErrorAction Stop
function GitHubJson([string[]]$Arguments) {
    $raw = & $gh.Source @Arguments
    if ($LASTEXITCODE -ne 0) { throw "GitHub CLI failed (exit $LASTEXITCODE)" }
    return ($raw | Out-String | ConvertFrom-Json)
}
$branch = GitHubJson -Arguments @('api',"repos/$Repository/branches/main")
$sha = [string]$branch.commit.sha
if ($sha -notmatch '^[0-9a-f]{40}$') { throw 'Invalid main SHA' }
$runs = GitHubJson -Arguments @('api',"repos/$Repository/actions/runs?head_sha=$sha&per_page=100")
$required = @('preflight','windows-bundle')
foreach ($name in $required) {
    $match = @($runs.workflow_runs | Where-Object {
        $_.name -eq $name -and $_.head_sha -eq $sha -and
        $_.head_branch -eq 'main' -and $_.event -eq 'push' -and
        $_.status -eq 'completed' -and $_.conclusion -eq 'success'
    } | Sort-Object run_number -Descending | Select-Object -First 1)
    if ($match.Count -ne 1) {
        throw "No successful main push $name run for $sha"
    }
    if ($name -eq 'windows-bundle') { $bundleRun = $match[0] }
}
Write-Output "Verified CI gates for main commit $sha"
if (-not $Download) {
    Write-Output 'Read-only discovery complete. Pass -Download to stage the verified bundle.'
    return
}
New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null
$destination = Join-Path $StageRoot $sha
if (Test-Path -LiteralPath $destination) {
    throw "Staging destination already exists; refusing to overwrite: $destination"
}
New-Item -ItemType Directory -Path $destination | Out-Null
try {
    & $gh.Source run download ([string]$bundleRun.id) --repo $Repository --name "BybitClusterGrid-windows-$sha" --dir $destination
    if ($LASTEXITCODE -ne 0) { throw 'Artifact download failed' }
    $zip = Join-Path $destination "BybitClusterGrid-$sha.zip"
    $checksum = "$zip.sha256"
    if (!(Test-Path -LiteralPath $zip) -or !(Test-Path -LiteralPath $checksum)) {
        throw 'Expected bundle and SHA256 checksum are missing'
    }
    $expected = (Get-Content -LiteralPath $checksum -Raw).Trim().Split(' ')[0].ToLowerInvariant()
    $actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -notmatch '^[0-9a-f]{64}$' -or $actual -ne $expected) {
        throw 'Bundle SHA256 mismatch'
    }
    Add-Type -AssemblyName System.IO.Compression
    $archive = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        $manifest = $archive.GetEntry('release-manifest.json')
        if ($null -eq $manifest) { throw 'Release manifest missing from ZIP' }
        $reader = New-Object IO.StreamReader($manifest.Open())
        try { $data = $reader.ReadToEnd() | ConvertFrom-Json }
        finally { $reader.Dispose() }
        if ($data.version -ne $sha) { throw 'Embedded release version mismatch' }
    }
    finally { $archive.Dispose() }
    Write-Output "STAGED_VERIFIED_RELEASE=$sha"
    Write-Output "STAGED_ZIP=$zip"
    Write-Output 'No running services or installed versions were modified.'
}
catch {
    Write-Warning "Staging failed; inspect/remove only the new directory: $destination"
    throw
}
