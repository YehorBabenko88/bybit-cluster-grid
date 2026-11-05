Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Net.Http
Add-Type -AssemblyName System.IO.Compression
$script:MirrorUrl='https://packages.chocolatey.org/NSSM.2.24.101.20180116.nupkg'
$script:OuterSha='6c6b1e287fb2ac6b04cfd32be2b9ed54a283cf0847fab2326e1b3961b512d340'
$script:InnerSha='99f5045fffbffb745d67fe3a065a953c4a3d9c253b868892d9b685b0ee7d07b8'
$script:PrimaryUrl='https://www.nssm.cc/ci/nssm-2.24-101-g897c7ad.zip'
$script:Member='tools/nssm-2.24-101-g897c7ad.zip'

function Test-NssmMirrorEligibility {
    param($Artifact,[int]$Status,[string]$MirrorOuterSha256)
    return ($Artifact.component -ceq 'nssm' -and $Artifact.url -ceq $script:PrimaryUrl -and
        $Artifact.filename -ceq 'nssm-2.24-101-g897c7ad.zip' -and $Artifact.sha256 -ceq $script:InnerSha -and
        $MirrorOuterSha256 -ceq $script:OuterSha -and $Status -in @(408,429,500,502,503,504))
}

function Receive-BoundedHttps {
    param([string]$Url,[string]$Destination,[long]$MaxBytes,[string]$Sha256,[long]$ExpectedBytes=0,[switch]$ExactUrl)
    $handler=[Net.Http.HttpClientHandler]::new();$handler.AllowAutoRedirect=$false
    $client=[Net.Http.HttpClient]::new($handler);$client.Timeout=[Threading.Timeout]::InfiniteTimeSpan
    $cancel=[Threading.CancellationTokenSource]::new([TimeSpan]::FromSeconds(240))
    $response=$null;$inputStream=$null;$output=$null;$owned=$false;$digest=$null
    try {
        $uri=[Uri]$Url
        for($redirect=0;$redirect -le 5;$redirect++) {
            if($uri.Scheme -cne 'https' -or $uri.UserInfo -or $uri.Fragment){throw 'VENDOR_HTTPS_REQUIRED'}
            $response=$client.GetAsync($uri,[Net.Http.HttpCompletionOption]::ResponseHeadersRead,$cancel.Token).GetAwaiter().GetResult()
            $status=[int]$response.StatusCode
            if($status -in @(301,302,303,307,308)) {
                if($ExactUrl -or $redirect -eq 5 -or !$response.Headers.Location){throw 'VENDOR_REDIRECT_REJECTED'}
                $uri=[Uri]::new($uri,$response.Headers.Location);$response.Dispose();$response=$null;continue
            }
            if($status -ne 200) {
                $exception=[InvalidOperationException]::new('VENDOR_HTTP_STATUS')
                $exception.Data['VendorHttpStatus']=$status
                throw $exception
            }
            break
        }
        if($response.Content.Headers.ContentLength -gt $MaxBytes){throw 'VENDOR_COMPRESSED_BUDGET'}
        $inputStream=$response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $output=[IO.File]::Open($Destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);$owned=$true
        $digest=[Security.Cryptography.SHA256]::Create();$buffer=New-Object byte[] 65536;[long]$total=0
        while(($n=$inputStream.ReadAsync($buffer,0,$buffer.Length,$cancel.Token).GetAwaiter().GetResult()) -gt 0) {
            $total+=$n;if($total -gt $MaxBytes){throw 'VENDOR_COMPRESSED_BUDGET'}
            $output.Write($buffer,0,$n);$null=$digest.TransformBlock($buffer,0,$n,$buffer,0)
        }
        $null=$digest.TransformFinalBlock([byte[]]@(),0,0);$actual=([BitConverter]::ToString($digest.Hash)).Replace('-','').ToLowerInvariant();$output.Dispose();$output=$null
        if($total -lt 1 -or ($ExpectedBytes -gt 0 -and $total -ne $ExpectedBytes) -or
            $actual -cne $Sha256){throw 'VENDOR_EXACT_BYTES_MISMATCH'}
        $owned=$false
    } catch {
        $status=$_.Exception.Data['VendorHttpStatus']
        $safe=[InvalidOperationException]::new('VENDOR_DOWNLOAD_REJECTED')
        if($null -ne $status){$safe.Data['VendorHttpStatus']=[int]$status}
        throw $safe
    } finally {
        if($null -ne $digest){$digest.Dispose()};if($null -ne $output){$output.Dispose()};if($null -ne $inputStream){$inputStream.Dispose()}
        if($null -ne $response){$response.Dispose()};$cancel.Dispose();$client.Dispose();$handler.Dispose()
        if($owned -and [IO.File]::Exists($Destination)){[IO.File]::Delete($Destination)}
    }
}

function Expand-PinnedNssmPackage {
    param([Parameter(Mandatory=$true)][string]$PackageFile,[Parameter(Mandatory=$true)][string]$Destination,
          [Parameter(Mandatory=$true)][string]$MirrorOuterSha256)
    $archive=$null;$file=$null;$output=$null;$inputStream=$null;$owned=$false;$digest=$null
    try {
        if($MirrorOuterSha256 -cne $script:OuterSha){throw 'MIRROR_CALLER_PIN'}
        $file=[IO.File]::Open($PackageFile,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
        if($file.Length -ne 417537){throw 'MIRROR_OUTER_BUDGET'}
        $hash=[Security.Cryptography.SHA256]::Create()
        try {$actual=([BitConverter]::ToString($hash.ComputeHash($file))).Replace('-','').ToLowerInvariant()}finally{$hash.Dispose()}
        if($actual -cne $MirrorOuterSha256){throw 'MIRROR_OUTER_PIN'}
        $file.Position=0;$archive=[IO.Compression.ZipArchive]::new($file,[IO.Compression.ZipArchiveMode]::Read,$true)
        if($archive.Entries.Count -gt 128){throw 'MIRROR_ENTRY_BUDGET'}
        $names=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        [long]$total=0;$target=$null
        foreach($entry in $archive.Entries) {
            $name=$entry.FullName
            if(!$names.Add($name) -or $name.StartsWith('/') -or $name.Contains('\') -or $name.Contains(':') -or
                @($name.Split('/') | Where-Object {$_ -eq '..' -or $_ -eq '.'}).Count -gt 0){throw 'MIRROR_ENTRY_NAME'}
            $kind=($entry.ExternalAttributes -shr 16) -band 0xf000
            if(($entry.ExternalAttributes -band 0x400) -ne 0 -or ($kind -ne 0 -and $kind -ne 0x8000 -and $kind -ne 0x4000)){throw 'MIRROR_LINK_ENTRY'}
            $total+=$entry.Length
            if($total -gt 16777216 -or $entry.Length -gt 16777216 -or
                ($entry.Length -gt 0 -and ($entry.CompressedLength -le 0 -or $entry.Length -gt 100*$entry.CompressedLength))){throw 'MIRROR_ZIP_BUDGET'}
            if($name -ceq $script:Member){$target=$entry}
        }
        if($null -eq $target -or $target.Length -ne 415458){throw 'MIRROR_MEMBER_REQUIRED'}
        $inputStream=$target.Open();$output=[IO.File]::Open($Destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);$owned=$true
        $digest=[Security.Cryptography.SHA256]::Create();$buffer=New-Object byte[] 65536;[long]$length=0
        while(($n=$inputStream.Read($buffer,0,$buffer.Length)) -gt 0) {
            $length+=$n;if($length -gt 415458){throw 'MIRROR_INNER_BUDGET'};$output.Write($buffer,0,$n);$null=$digest.TransformBlock($buffer,0,$n,$buffer,0)
        }
        $null=$digest.TransformFinalBlock([byte[]]@(),0,0);$actual=([BitConverter]::ToString($digest.Hash)).Replace('-','').ToLowerInvariant();$output.Dispose();$output=$null
        if($length -ne 415458 -or $actual -cne $script:InnerSha){throw 'MIRROR_INNER_PIN'}
        $owned=$false
    } catch {throw [InvalidOperationException]::new('MIRROR_PACKAGE_REJECTED')} finally {
        if($null -ne $digest){$digest.Dispose()};if($null -ne $output){$output.Dispose()};if($null -ne $inputStream){$inputStream.Dispose()}
        if($null -ne $archive){$archive.Dispose()};if($null -ne $file){$file.Dispose()}
        if($owned -and [IO.File]::Exists($Destination)){[IO.File]::Delete($Destination)}
    }
}

function Save-PinnedNssmMirrorPackage {
    param([Parameter(Mandatory=$true)][string]$Destination,[Parameter(Mandatory=$true)][string]$MirrorOuterSha256)
    if($MirrorOuterSha256 -cne $script:OuterSha){throw [InvalidOperationException]::new('MIRROR_CALLER_PIN')}
    Receive-BoundedHttps -Url $script:MirrorUrl -Destination $Destination -MaxBytes 417537 -ExpectedBytes 417537 -Sha256 $MirrorOuterSha256 -ExactUrl
}
function Save-PinnedVendorArtifact {
    param([Parameter(Mandatory=$true)]$Artifact,[Parameter(Mandatory=$true)][string]$Destination,
          [string]$MirrorOuterSha256)
    $expected=0;if($null -ne $Artifact.expected_bytes){$expected=[long]$Artifact.expected_bytes}
    $status=0
    try {
        Receive-BoundedHttps -Url $Artifact.url -Destination $Destination -MaxBytes $Artifact.max_bytes -Sha256 $Artifact.sha256 -ExpectedBytes $expected
        return [ordered]@{component=$Artifact.component;transport='HTTPS_PRIMARY';origin=$Artifact.url;sha256=$Artifact.sha256;native_execution='NOT_RUN'}
    } catch {
        if($null -ne $_.Exception.Data['VendorHttpStatus']){$status=[int]$_.Exception.Data['VendorHttpStatus']}
        if(!(Test-NssmMirrorEligibility $Artifact $status $MirrorOuterSha256)){throw [InvalidOperationException]::new('VENDOR_PRIMARY_REJECTED')}
    }
    $package=$Destination+'.mirror-'+[Guid]::NewGuid().ToString('N');$packageOwned=$false
    try {
        Save-PinnedNssmMirrorPackage -Destination $package -MirrorOuterSha256 $MirrorOuterSha256
        $packageOwned=$true
        Expand-PinnedNssmPackage -PackageFile $package -Destination $Destination -MirrorOuterSha256 $MirrorOuterSha256
        return [ordered]@{component='nssm';transport='HTTPS_MIRROR_PACKAGE_BYTE_IDENTICAL';origin=$script:PrimaryUrl;primary_status=$status;mirror_url=$script:MirrorUrl;mirror_sha256=$MirrorOuterSha256;member=$script:Member;sha256=$script:InnerSha;native_execution='NOT_RUN'}
    } finally {if($packageOwned -and [IO.File]::Exists($package)){[IO.File]::Delete($package)}}
}
Export-ModuleMember -Function Save-PinnedNssmMirrorPackage,Save-PinnedVendorArtifact,Expand-PinnedNssmPackage,Test-NssmMirrorEligibility


