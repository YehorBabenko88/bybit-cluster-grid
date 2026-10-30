"""Pure conservative ACL snapshot review, never AccessCheck or bootstrap authority.

Raw ACE flags use Win32 ACE_HEADER values, not .NET PropagationFlags values.
No host APIs, paths, SID resolution, token membership inference or mutations.
The supported subset intentionally cannot certify real Known Folder custody.
"""
import ntpath
import re

_REPLACEMENT = 0x40 | 0x10000 | 0x40000 | 0x80000 | 0x10000000 | 0x40000000
_CHILD_MUTATION = _REPLACEMENT | 2 | 4 | 16 | 256
# Supported file/directory rights, standard rights and generic rights only.
# Reserved bits, MAXIMUM_ALLOWED and ACCESS_SYSTEM_SECURITY are not modeled.
_SUPPORTED_MASK = 0xF01F01FF
_SY, _BA = 'S-1-5-18', 'S-1-5-32-544'


def _sid(value):
    if type(value) is not str or len(value) > 184:
        return False
    if re.fullmatch(r'S-1-(?:0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*)){1,15}', value) is None:
        return False
    parts = value.split('-')
    return int(parts[2]) < 2**48 and all(int(v) < 2**32 for v in parts[3:])


def _exact(value, keys):
    return type(value) is dict and set(value) == set(keys)


def review_snapshot(snapshot):
    """Return conditional ACL risk only. Every host/execution gate stays blocked.

    Deny ACEs, MIC, restricted tokens, privileges, capabilities and AccessCheck
    order are NOT evaluated. A dangerous allow is a conservative blocker, not
    a demonstrated exploit. Inherit-only does not grant rights on this object;
    it can still expose unprotected future children. Protected child DACLs do
    not erase parent DELETE_CHILD/WRITE_DAC/WRITE_OWNER hazards.
    """
    findings = set()
    result = dict(model='BLOCKED', host='BLOCKED', execute=False, cleanup=False,
                  effective_access='NOT_EVALUATED', findings=[])
    if not _exact(snapshot, ('schema', 'operator_sid', 'ancestors')):
        findings.add('INVALID_SNAPSHOT')
    else:
        user = snapshot['operator_sid']
        chain = snapshot['ancestors']
        if (type(snapshot['schema']) is not int or snapshot['schema'] != 1
                or not _sid(user) or not user.startswith('S-1-5-21-')
                or len(user.split('-')) != 8
                or type(chain) is not list or not 1 <= len(chain) <= 64):
            findings.add('INVALID_SNAPSHOT')
        else:
            trusted = {user, _SY, _BA}
            seen = set()
            for parent in chain:
                if not _exact(parent, ('identity', 'owner', 'dacl_present', 'reparse', 'complete', 'aces')):
                    findings.add('INCOMPLETE_ANCESTRY'); continue
                identity = parent['identity']
                if type(identity) is not str or not identity or len(identity) > 256 or identity in seen:
                    findings.add('UNKNOWN_OR_DUPLICATE_IDENTITY')
                else:
                    seen.add(identity)
                if not _sid(parent['owner']) or parent['owner'] not in trusted:
                    findings.add('UNKNOWN_OWNER')
                if (parent['dacl_present'] is not True or parent['reparse'] is not False
                        or parent['complete'] is not True):
                    findings.add('INCOMPLETE_ANCESTRY')
                aces = parent['aces']
                if type(aces) is not list or not 1 <= len(aces) <= 1024:
                    findings.add('UNKNOWN_DACL'); continue
                for ace in aces:
                    if not _exact(ace, ('sid', 'mask', 'flags', 'kind')):
                        findings.add('UNSUPPORTED_ACE'); continue
                    sid, mask, flags, kind = (ace[k] for k in ('sid', 'mask', 'flags', 'kind'))
                    if (not _sid(sid) or type(mask) is not int or not 0 <= mask < 2**32
                            or mask & ~_SUPPORTED_MASK
                            or type(flags) is not int or not 0 <= flags <= 31
                            or type(kind) is not int or kind not in (0, 1)):
                        findings.add('UNSUPPORTED_ACE'); continue
                    if kind == 0 and sid not in trusted:
                        if not flags & 8 and mask & _REPLACEMENT:
                            findings.add('UNTRUSTED_EFFECTIVE_MUTATION')
                        if flags & 3 and mask & _CHILD_MUTATION:
                            findings.add('UNTRUSTED_INHERITABLE_MUTATION')
    result['findings'] = sorted(findings)
    if not findings:
        result['model'] = 'OFFLINE_MODEL_PASS'
    return result


def review_profile_candidate(proposal):
    """Synthetic proposed UserProfile contract, not a Known Folder API call.

    Input booleans/identities are hypothetical evidence, not observations or
    authorization. Host/execute/cleanup remain blocked even for a model PASS.
    """
    result = dict(model='BLOCKED', host='BLOCKED', execute=False, cleanup=False,
                  effective_access='NOT_EVALUATED', findings=['INVALID_PROFILE_PROPOSAL'])
    strings = ('mode', 'known_folder_id', 'htoken', 'profile_path', 'token_profile_path',
               'os_volume', 'target', 'filesystem', 'token_sid', 'parent_identity')
    keys = (*strings, 'flags', 'target_absent', 'profile_mount', 'source_links',
            'source_reparse', 'standard_token', 'thread_token_absent',
            'package_identity_absent', 'parent_acl', 'ancestor_paths')
    if not _exact(proposal, keys) or not all(type(proposal[k]) is str for k in strings):
        return result
    p = proposal
    if (p['mode'] != 'USER_PROFILE_V1_DESIGN'
            or p['known_folder_id'] != '5e6c858f-0e22-4760-9afe-ea3317b67173'
            or type(p['flags']) is not int or p['flags'] != 0x4000
            or p['htoken'] != 'CURRENT_USER_NULL' or p['filesystem'] != 'NTFS'
            or p['target_absent'] is not True or p['profile_mount'] is not False
            or type(p['source_links']) is not int or p['source_links'] != 1
            or p['source_reparse'] is not False or p['standard_token'] is not True
            or p['thread_token_absent'] is not True or p['package_identity_absent'] is not True):
        return result
    profile, target = p['profile_path'], p['target']
    if (re.fullmatch(r'[A-Z]:\\', p['os_volume']) is None
            or p['token_profile_path'] != profile
            or not profile.startswith(p['os_volume']) or profile == p['os_volume']
            or ntpath.dirname(target) != profile
            or re.fullmatch(r'GridS0Package-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',
                            ntpath.basename(target)) is None):
        return result
    for path in (profile, target):
        try:
            if len(path.encode('utf-16le')) > 480:
                return result
        except UnicodeError:
            return result
        if ntpath.normpath(path) != path or '/' in path:
            return result
        for part in path[3:].split('\\'):
            if (not part or part.rstrip(' .') != part
                    or any(ord(c) < 32 or c in ':<>"|?*%~' for c in part)
                    or re.fullmatch(r'CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[0-9¹²³]|LPT[0-9¹²³]',
                                    part.split('.')[0].upper()) is not None):
                return result
    result = review_snapshot(p['parent_acl'])
    if result['model'] != 'OFFLINE_MODEL_PASS':
        return result
    parent = p['parent_acl']
    expected_paths = [p['os_volume']]
    for part in profile[3:].split('\\'):
        expected_paths.append(ntpath.join(expected_paths[-1], part))
    if (p['token_sid'] != parent['operator_sid']
            or type(p['ancestor_paths']) is not list or p['ancestor_paths'] != expected_paths
            or len(parent['ancestors']) != len(expected_paths)
            or p['parent_identity'] != parent['ancestors'][-1]['identity']):
        result['model'] = 'BLOCKED'; result['findings'] = ['PROFILE_IDENTITY_MISMATCH']
    return result
