param(
 [Parameter(Mandatory=$true)][string]$CoordinatorUrl,
 [Parameter(Mandatory=$true)][string]$DataRoot,
 [int]$TimeoutSeconds=120
)
$ErrorActionPreference="Stop"
$secret=Join-Path $DataRoot "secrets"
$nodeFile=Join-Path $secret "node.id"
$credFile=Join-Path $secret "node.credential"
if(!(Test-Path $nodeFile) -or !(Test-Path $credFile)){throw "Worker identity is missing after installation"}
$node=(Get-Content $nodeFile -Raw).Trim()
$credential=(Get-Content $credFile -Raw).Trim()
if(!$node -or !$credential){throw "Worker identity is empty after installation"}
$uri=$CoordinatorUrl.TrimEnd("/")+"/nodes/"+[Uri]::EscapeDataString($node)+"/acceptance"
$deadline=(Get-Date).AddSeconds([Math]::Max(10,$TimeoutSeconds))
$last=""
while((Get-Date) -lt $deadline){
    try{
        $r=Invoke-RestMethod -Method Get -Uri $uri -Headers @{"X-Node-Credential"=$credential} -TimeoutSec 10
        if($r.accepted -eq $true){
            Write-Host "Worker accepted by CONTROL: $node"
            $credential=$null
            exit 0
        }
        $last=[string]$r.reason
    }catch{
        $last=$_.Exception.Message
    }
    Start-Sleep -Seconds 2
}
$credential=$null
throw "Worker task started but CONTROL did not observe a healthy heartbeat within $TimeoutSeconds seconds. Last result: $last"
