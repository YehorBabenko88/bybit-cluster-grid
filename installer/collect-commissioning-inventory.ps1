# Read-only Windows fleet inventory for commissioning.
# Never collects credentials, environment variables, private keys or database rows.
# Run locally on each node in PowerShell 5.1+; does not require administrator rights.
[CmdletBinding()]
param(
    [string]$OutputPath = "",
    [string]$GridRoot = "$env:ProgramFiles\BybitClusterGrid"
)
$ErrorActionPreference = "Stop"
function Read-Marker([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $value = (Get-Content -LiteralPath $Path -Raw).Trim()
    if ($value -cmatch '^[0-9a-f]{40}$') { return $value }
    return "INVALID_OR_UNRECOGNIZED"
}
function Drive-Info([string]$Path) {
    $root = [System.IO.Path]::GetPathRoot($Path)
    if (-not $root) { return $null }
    $drive = Get-PSDrive -Name ($root.Substring(0,1)) -PSProvider FileSystem -ErrorAction SilentlyContinue
    if (-not $drive) { return $null }
    return [ordered]@{ root=$root; free_bytes=$drive.Free; used_bytes=$drive.Used }
}
$processes = @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^(python|pythonw|postgres|pg_ctl|ssh|tailscale)(\.exe)?$' } |
        ForEach-Object {
            # Intentionally omit CommandLine: it may contain secrets.
            [ordered]@{ pid=$_.ProcessId; name=$_.Name; parent_pid=$_.ParentProcessId }
        }
)
$tasks = @(
    Get-ScheduledTask -ErrorAction SilentlyContinue |
        Where-Object { $_.TaskName -match 'grid|bybit|strattester|terminan' } |
        ForEach-Object { [ordered]@{ name=$_.TaskName; path=$_.TaskPath; state=[string]$_.State } }
)
$services = @(
    Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'grid|bybit|strattester|terminan|postgres' -or $_.DisplayName -match 'grid|bybit|strattester|terminan' } |
        ForEach-Object { [ordered]@{ name=$_.Name; state=$_.State; start_mode=$_.StartMode } }
)
$report = [ordered]@{
    schema = 1
    collected_utc = [DateTime]::UtcNow.ToString("o")
    computer_name = $env:COMPUTERNAME
    os = [Environment]::OSVersion.VersionString
    powershell_version = $PSVersionTable.PSVersion.ToString()
    grid_root_exists = Test-Path -LiteralPath $GridRoot
    grid_current_sha = Read-Marker (Join-Path $GridRoot "current.version")
    grid_previous_sha = Read-Marker (Join-Path $GridRoot "previous.version")
    disk = Drive-Info $GridRoot
    processes = $processes
    scheduled_tasks = $tasks
    services = $services
    unknowns = @("tailscale_ip","ssh_routes","postgres_schema_version","database_backup_verified","wal_roots","postgres_role_permissions","network_failover","physical_power_loss")
}
$json = $report | ConvertTo-Json -Depth 7
if ($OutputPath) {
    $full = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
    $dir = Split-Path -Parent $full
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) { throw "Output directory must exist: $dir" }
    if (Test-Path -LiteralPath $full) { throw "Refusing to overwrite existing inventory: $full" }
    # Exclusive creation closes the Test-Path/write race; another inventory
    # writer's file is never overwritten, including case-insensitive aliases.
    $stream=[System.IO.File]::Open($full,[System.IO.FileMode]::CreateNew,
                                 [System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
    try {
        $bytes=(New-Object System.Text.UTF8Encoding($false)).GetBytes($json)
        $stream.Write($bytes,0,$bytes.Length)
        $stream.Flush($true)
    } finally { $stream.Dispose() }
    Write-Output "Inventory saved: $full"
} else {
    Write-Output $json
}
