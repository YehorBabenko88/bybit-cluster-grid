# Injectable read-only inventory. Production providers are supplied only in CollectLocal.
function Get-LsaCandidateInventory {
    param([scriptblock]$Users,[scriptblock]$Groups,[scriptblock]$Members)
    $result=@{ candidates=[ordered]@{}; errors=@(); completeness='UNKNOWN' }
    try {
        $usersFound=@(& $Users)
        if ($usersFound.Count -ne 2) { throw 'USER_COUNT' }
        foreach ($user in $usersFound) {
            if ($user.Name -cnotin @('GridLabCollector','GridLabStorage') -or
                $user.SID.Value -cnotmatch '^S-1-5-21-[0-9]+-[0-9]+-[0-9]+-[0-9]+$' -or
                $result.candidates.Contains($user.SID.Value)) { throw 'AMBIGUOUS_IDENTITY' }
            $result.candidates[$user.SID.Value]=@{alias=$user.Name; relation='LOCAL_ACCOUNT'}
        }
        foreach ($group in @(& $Groups)) {
            $membersFound=@(& $Members $group)
            foreach ($user in $usersFound) {
                if (@($membersFound | Where-Object { $_.SID.Value -eq $user.SID.Value }).Count) {
                    if (-not $result.candidates.Contains($group.SID.Value)) {
                        $result.candidates[$group.SID.Value]=@{alias=('local_group_'+$result.candidates.Count); relation='DIRECT_LOCAL_GROUP'}
                    }
                }
            }
        }
    } catch { $result.errors += 'LOCAL_IDENTITY_OR_GROUP_ENUMERATION_FAILED' }
    return $result
}
