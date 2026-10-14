#Requires -Version 5.1
# Read-only evidence; callers must hold Global\BybitClusterGridReleaseSwitch.
function Assert-GridRuntimeStopped {
    [CmdletBinding()]
    param()
    # Capture diagnostics too: providers must not leak command lines or credentials.
    try { $tasks = @(Get-ScheduledTask -ErrorAction Stop *>&1) }
    catch { throw 'GRID_RUNTIME_TASK_INVENTORY_FAILED' }
    foreach ($task in $tasks) {
        if ($null -eq $task -or $task -is [System.Management.Automation.ErrorRecord] -or
            [string]::IsNullOrWhiteSpace([string]$task.TaskName)) {
            throw 'GRID_RUNTIME_TASK_INVENTORY_INVALID'
        }
        if ($task.TaskName -in @('BybitClusterGridAgent','BybitClusterGridCoordinator','BybitClusterGridArchivePipeline')) {
            if ([string]$task.State -ne 'Disabled' -or
                ($null -ne $task.Settings -and $task.Settings.Enabled -eq $true)) {
                throw 'GRID_RUNTIME_TASK_NOT_DISABLED'
            }
        }
    }
    # No Name filter: console entry points and non-Python launchers matter too.
    try { $processes = @(Get-CimInstance -ClassName Win32_Process -OperationTimeoutSec 10 -ErrorAction Stop *>&1) }
    catch { throw 'GRID_RUNTIME_PROCESS_INVENTORY_FAILED' }
    if ($processes.Count -eq 0) { throw 'GRID_RUNTIME_PROCESS_INVENTORY_EMPTY' }
    foreach ($process in $processes) {
        if ($null -eq $process -or $process -is [System.Management.Automation.ErrorRecord] -or
            [string]::IsNullOrWhiteSpace([string]$process.Name)) {
            throw 'GRID_RUNTIME_PROCESS_INVENTORY_INVALID'
        }
        if ($null -ne $process.CommandLine -and $process.CommandLine -isnot [string]) {
            throw 'GRID_RUNTIME_PROCESS_INVENTORY_INVALID'
        }
        $name = [string]$process.Name
        $command = [string]$process.CommandLine
        if ($name -match '^(python[^\\/\s]*|pyw?|pwsh|powershell|uvicorn)([.]exe)?$' -and
            [string]::IsNullOrWhiteSpace($command)) {
            throw 'GRID_RUNTIME_PROCESS_IDENTITY_UNKNOWN'
        }
        if ($command -match '(?i)(\bgrid[.](worker|coordinator|archive_service|release_supervisor)\b|\bgrid[.][a-z_][a-z0-9_]*|\brun_(worker|coordinator)[.]py\b|\bgrid[\\/][a-z_][a-z0-9_]*[.]py\b|\b(from\s+grid\s+import|import\s+grid\b)|\b(coordinator-launcher|archive-launcher|launcher)[.]ps1\b)') {
            throw 'GRID_RUNTIME_PROCESS_ACTIVE'
        }
    }
}
