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
& icacls $SecretDir /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)(F)" "*S-1-5-32-544:(OI)(CI)(F)" | Out-Null
if($LASTEXITCODE -ne 0){throw "Failed to protect Grid secret directory ACL"}
& icacls $CredentialFile /inheritance:r /grant:r "*S-1-5-18:(F)" "*S-1-5-32-544:(F)" | Out-Null
if($LASTEXITCODE -ne 0){throw "Failed to protect node credential ACL"}
& icacls $NodeIdFile /inheritance:r /grant:r "*S-1-5-18:(F)" "*S-1-5-32-544:(F)" | Out-Null
if($LASTEXITCODE -ne 0){throw "Failed to protect node id ACL"}
@{node_id=$r.node_id;credential_file=$CredentialFile;node_id_file=$NodeIdFile;install_mode=$r.install_mode} | ConvertTo-Json
