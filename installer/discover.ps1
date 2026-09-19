$ErrorActionPreference="Stop"

function Get-PythonCandidates {
    $items=@()
    foreach($cmd in @("py.exe","python.exe","python3.exe")) {
        $c=Get-Command $cmd -ErrorAction SilentlyContinue
        if($c) {
            try {
                if($cmd -eq "py.exe") {
                    $v=& $c.Source -3 -c "import sys; print('.'.join(map(str,sys.version_info[:3])))" 2>$null
                    $exe=& $c.Source -3 -c "import sys; print(sys.executable)" 2>$null
                } else {
                    $v=& $c.Source -c "import sys; print('.'.join(map(str,sys.version_info[:3])))" 2>$null
                    $exe=& $c.Source -c "import sys; print(sys.executable)" 2>$null
                }
                if($LASTEXITCODE -eq 0) { $items += [pscustomobject]@{exe=$exe;version=$v;source=$cmd} }
            } catch {}
        }
    }
    $items | Sort-Object exe -Unique
}

function Get-PostgresCandidates {
    $items=@()
    $pg=Get-Command pg_config.exe -ErrorAction SilentlyContinue
    if($pg) {
        try { $items += [pscustomobject]@{source="PATH";bin=Split-Path $pg.Source;version=(& $pg.Source --version)} } catch {}
    }
    Get-Service -ErrorAction SilentlyContinue | Where-Object {$_.Name -match "postgres"} | ForEach-Object {
        $svc=$_
        $path=(Get-CimInstance Win32_Service -Filter "Name='$($svc.Name)'" -ErrorAction SilentlyContinue).PathName
        $items += [pscustomobject]@{source="service";service=$svc.Name;status=$svc.Status.ToString();path=$path}
    }
    foreach($root in @("HKLM:\SOFTWARE\PostgreSQL\Installations","HKLM:\SOFTWARE\WOW6432Node\PostgreSQL\Installations")) {
        if(Test-Path $root) {
            Get-ChildItem $root | ForEach-Object {
                $p=Get-ItemProperty $_.PSPath
                $items += [pscustomobject]@{source="registry";version=$p.Version;base=$p."Base Directory";data=$p."Data Directory";port=$p.Port}
            }
        }
    }
    $items
}

$report=[ordered]@{
    computer=$env:COMPUTERNAME
    os=(Get-CimInstance Win32_OperatingSystem).Caption
    architecture=$env:PROCESSOR_ARCHITECTURE
    python=@(Get-PythonCandidates)
    postgres=@(Get-PostgresCandidates)
    postgres_port_5432=(Test-NetConnection 127.0.0.1 -Port 5432 -WarningAction SilentlyContinue).TcpTestSucceeded
    existing_grid_task=[bool](Get-ScheduledTask -TaskName "BybitClusterGridAgent" -ErrorAction SilentlyContinue)
    existing_grid_dir=(Test-Path "$env:ProgramFiles\BybitClusterGrid")
    data_dir=(Test-Path "$env:ProgramData\BybitClusterGrid")
}
$report | ConvertTo-Json -Depth 8
