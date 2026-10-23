#Requires -Version 5.1
$ErrorActionPreference='Stop'
Get-ChildItem (Split-Path $PSScriptRoot -Parent) -Recurse -Filter '*.ps1' | ForEach-Object {
 $t=$null;$e=$null;[void][Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$t,[ref]$e)
 if($e.Count){throw 'PS_PARSE_FAILED'}
}
$r=@(& (Join-Path $PSScriptRoot 'test-ls5-acl-planonly.ps1'))
if($r -notcontains 'LS5_PLAN_ONLY_CASES=13; NO_HOST_OBSERVATIONS; NO_AUTHORITY'){throw 'PLANONLY_INVENTORY_FAILED'}
$r
