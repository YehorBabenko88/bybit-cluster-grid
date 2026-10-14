$ErrorActionPreference='Stop'
$global:GridStageBadGate=$false
function Get-Command {param($Name,$ErrorAction) [pscustomobject]@{Source='Invoke-FixtureGitHub'}}
function Invoke-FixtureGitHub {
 $global:LASTEXITCODE=0
 if($args[0] -ne 'api'){throw 'Fixture forbids download or other GitHub mutations'}
 if($args[1] -like '*/branches/*'){@{commit=@{sha=('a'*40)}} | ConvertTo-Json -Depth 5;return}
 $runs=@('preflight','windows-bundle','commissioning-manifest','composed-safety-gate','windows-commissioning') | ForEach-Object {
  @{name=$_;head_sha=('a'*40);head_branch='audit/codex-fixture';event='pull_request';status='completed';conclusion=$(if($global:GridStageBadGate -and $_ -eq 'windows-commissioning'){'failure'}else{'success'});id=1;run_number=1}
 }
 if($global:GridStageBadGate){$runs+=@{name='windows-commissioning';head_sha=('a'*40);head_branch='audit/codex-fixture';event='pull_request';status='completed';conclusion='success';id=0;run_number=0}}
 @{workflow_runs=@($runs)} | ConvertTo-Json -Depth 6
}
$script=Join-Path $PSScriptRoot '..\stage-github-release.ps1'
$result=& $script -Branch audit/codex-fixture -Commit ('a'*40) -AllowAuditCandidate
if(($result | Out-String) -notmatch 'Read-only discovery complete'){throw 'Audit staging plan did not verify exact gates'}
$global:GridStageBadGate=$true
$rejected=$false
try {& $script -Branch audit/codex-fixture -Commit ('a'*40) -AllowAuditCandidate} catch {$rejected=$true}
if(!$rejected){throw 'A failed exact-head commissioning gate was accepted'}
Write-Output 'Audit staging fixture passed; no network or files changed'
