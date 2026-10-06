param(
 [Parameter(Mandatory=$true)][string]$CoordinatorUrl,
 [Parameter(Mandatory=$true)][string]$EnrollmentToken,
 [Parameter(Mandatory=$true)][string]$Python,
 [Parameter(Mandatory=$true)][string]$DataRoot
)
$ErrorActionPreference="Stop"
$NodeId=& $Python -c "from grid.resources import NODE_ID; print(NODE_ID)"
if($LASTEXITCODE -ne 0 -or !$NodeId){throw "Unable to determine node id"}
$body=@{node_id=$NodeId.Trim();enrollment_token=$EnrollmentToken} | ConvertTo-Json
$r=Invoke-RestMethod -Method Post -Uri ($CoordinatorUrl.TrimEnd("/")+"/enroll") -ContentType "application/json" -Body $body
if(!$r.credential){throw "Coordinator did not return node credential"}
if($r.install_mode -notin @("PILOT","NORMAL")){throw "Coordinator did not return an authorized install mode"}
$SecretDir=Join-Path $DataRoot "secrets"
New-Item -ItemType Directory -Force -Path $SecretDir | Out-Null
$CredentialFile=Join-Path $SecretDir "node.credential"
Set-Content -Path $CredentialFile -Value $r.credential -NoNewline -Encoding ascii
$NodeIdFile=Join-Path $SecretDir "node.id"
Set-Content -Path $NodeIdFile -Value $r.node_id -NoNewline -Encoding ascii
& icacls $SecretDir /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" | Out-Null
& icacls $CredentialFile /inheritance:r /grant:r "SYSTEM:F" "Administrators:F" | Out-Null
& icacls $NodeIdFile /inheritance:r /grant:r "SYSTEM:F" "Administrators:F" | Out-Null
@{node_id=$r.node_id;credential_file=$CredentialFile;node_id_file=$NodeIdFile;install_mode=$r.install_mode} | ConvertTo-Json
