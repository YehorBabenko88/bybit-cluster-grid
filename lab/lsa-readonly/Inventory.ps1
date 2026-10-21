# Injectable read-only inventory. Production providers are supplied only in CollectLocal.
function Get-LsaCandidateInventory {
    param([scriptblock]$Users,[scriptblock]$Groups,[scriptblock]$Members)
    $ErrorActionPreference='Stop'
    $result=@{ candidates=[ordered]@{}; errors=@(); completeness='UNKNOWN' }
    try {
        $usersFound=@(& $Users 2>&1)
        if ($usersFound.Count -ne 2) { throw 'USER_COUNT' }
        $names=@()
        foreach ($user in $usersFound) {
            if ($user -is [System.Management.Automation.ErrorRecord] -or
                $user.Name -cnotin @('GridLabCollector','GridLabStorage') -or $user.Name -cin $names -or
                $user.SID.Value -cnotmatch '^S-1-5-21-[0-9]+-[0-9]+-[0-9]+-[0-9]+$' -or
                $result.candidates.Contains($user.SID.Value)) { throw 'AMBIGUOUS_IDENTITY' }
            if (([System.Security.Principal.SecurityIdentifier]::new($user.SID.Value)).Value -cne $user.SID.Value) { throw 'INVALID_SID' }
            $names+= $user.Name
            $result.candidates[$user.SID.Value]=@{alias=$user.Name; relation='LOCAL_ACCOUNT'}
        }
        $groupSids=@()
        foreach ($group in @(& $Groups 2>&1)) {
            if ($group -is [System.Management.Automation.ErrorRecord] -or
                ([System.Security.Principal.SecurityIdentifier]::new($group.SID.Value)).Value -cne $group.SID.Value -or
                $group.SID.Value -cin $groupSids -or $result.candidates.Contains($group.SID.Value)) { throw 'INVALID_GROUP' }
            $groupSids+= $group.SID.Value
            $membersFound=@(& $Members $group 2>&1)
            foreach ($member in $membersFound) {
                if ($member -is [System.Management.Automation.ErrorRecord] -or
                    ([System.Security.Principal.SecurityIdentifier]::new($member.SID.Value)).Value -cne $member.SID.Value) { throw 'INVALID_MEMBER' }
            }
            foreach ($user in $usersFound) {
                if (@($membersFound | Where-Object { $_.SID.Value -eq $user.SID.Value }).Count) {
                    if (-not $result.candidates.Contains($group.SID.Value)) {
                        $result.candidates[$group.SID.Value]=@{alias=('local_group_'+$result.candidates.Count); relation='DIRECT_LOCAL_GROUP'}
                    }
                }
            }
        }
    } catch {
        # Never expose a partial snapshot as usable candidate evidence.
        $result.candidates=[ordered]@{}
        $result.errors += 'LOCAL_IDENTITY_OR_GROUP_ENUMERATION_FAILED'
    }
    return $result
}
