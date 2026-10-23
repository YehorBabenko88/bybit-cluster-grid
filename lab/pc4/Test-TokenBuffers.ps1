#Requires -Version 5.1
# Synthetic unmanaged buffers only. NEVER Read/OpenProcess/GetTokenInformation.
$ErrorActionPreference='Stop'
Add-Type -Path (Join-Path $PSScriptRoot 'TokenFacts.cs')
$script:cases=0
function Check([bool]$Value){if(!$Value){throw 'BUFFER_ASSERT_FAILED'};$script:cases++}
function Reject([scriptblock]$Action){$bad=$false;try{& $Action|Out-Null}catch{$bad=$true};Check $bad}
$offset=if([IntPtr]::Size -eq 8){8}else{4}
$stride=if([IntPtr]::Size -eq 8){16}else{8}
$size=128;$b=[Runtime.InteropServices.Marshal]::AllocHGlobal($size)
try {
 $sid=New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')
 $bytes=New-Object byte[] $sid.BinaryLength;$sid.GetBinaryForm($bytes,0)
 $sidPointer=[IntPtr]::Add($b,64)
 [Runtime.InteropServices.Marshal]::Copy($bytes,0,$sidPointer,$bytes.Length)
 [Runtime.InteropServices.Marshal]::WriteInt32($b,1)
 [Runtime.InteropServices.Marshal]::WriteIntPtr($b,$offset,$sidPointer)
 foreach($row in @(@(4,$true),@(0,$false),@(16,$false),@(20,$false),@(7,$true))){
  [Runtime.InteropServices.Marshal]::WriteInt32($b,($offset+[IntPtr]::Size),[int]$row[0])
  Check ([GridPc4.TokenFacts]::ParseGroupBuffer($b,$size) -eq $row[1])
  Check ([GridPc4.TokenFacts]::HasAdministratorGroup($b,$size))
 }
 [Runtime.InteropServices.Marshal]::WriteInt32($sidPointer,12,545)
 Check (![GridPc4.TokenFacts]::HasAdministratorGroup($b,$size))
 Check (![GridPc4.TokenFacts]::ParseGroupBuffer($b,$size))
 [Runtime.InteropServices.Marshal]::WriteInt32($sidPointer,12,544)
 Reject {[GridPc4.TokenFacts]::ParseGroupBuffer($b,3)}
 Reject {[GridPc4.TokenFacts]::ParseGroupBuffer([IntPtr]::Zero,128)}
 Reject {[GridPc4.TokenFacts]::ParseGroupBuffer($b,($offset+$stride-1))}
 [Runtime.InteropServices.Marshal]::WriteInt32($b,513)
 Reject {[GridPc4.TokenFacts]::ParseGroupBuffer($b,$size)}
 [Runtime.InteropServices.Marshal]::WriteInt32($b,-1)
 Reject {[GridPc4.TokenFacts]::ParseGroupBuffer($b,$size)}
 [Runtime.InteropServices.Marshal]::WriteInt32($b,1)
 foreach($pointer in @([IntPtr]::Zero,[IntPtr]::Add($b,-1),[IntPtr]::Add($b,$size-4),[IntPtr]::Add($b,$size))){
  [Runtime.InteropServices.Marshal]::WriteIntPtr($b,$offset,$pointer)
  Reject {[GridPc4.TokenFacts]::ParseGroupBuffer($b,$size)}
 }
 [Runtime.InteropServices.Marshal]::WriteIntPtr($b,$offset,$sidPointer)
 [Runtime.InteropServices.Marshal]::WriteByte($sidPointer,0,2)
 Reject {[GridPc4.TokenFacts]::ParseGroupBuffer($b,$size)}
 [Runtime.InteropServices.Marshal]::WriteByte($sidPointer,0,1)
 [Runtime.InteropServices.Marshal]::WriteInt32($b,($offset+[IntPtr]::Size),128)
 Reject {[GridPc4.TokenFacts]::ParseGroupBuffer($b,$size)}
 [Runtime.InteropServices.Marshal]::WriteInt32($b,($offset+[IntPtr]::Size),4)
 [Runtime.InteropServices.Marshal]::WriteByte($sidPointer,1,255)
 Reject {[GridPc4.TokenFacts]::ParseGroupBuffer($b,$size)}
} finally {[Runtime.InteropServices.Marshal]::FreeHGlobal($b)}
Write-Output ('TOKEN_BUFFER_CASES='+$script:cases+'; SYNTHETIC_ONLY; PHYSICAL_NOT_RUN')
