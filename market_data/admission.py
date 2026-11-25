"""Module-side enforcement of Unified's in-memory admission callback."""
import os
import re


def startup_identity(startup_admission):
    module_id = os.environ.get('UNIFIED_MODULE_ID')
    if module_id is None:
        return None
    token = os.environ.get('UNIFIED_INSTANCE_TOKEN', '')
    version = os.environ.get('UNIFIED_MODULE_VERSION', '')
    release_id = os.environ.get('UNIFIED_RELEASE_ID', '')
    if (module_id != 'market_data' or re.fullmatch('[0-9a-f]{64}', token) is None
            or not version or len(version) > 128 or not release_id or len(release_id) > 128):
        raise RuntimeError('managed market data identity refused')
    if (startup_admission is None or not callable(getattr(startup_admission, 'require_current', None))
            or startup_admission.require_current() is not True):
        raise RuntimeError('current managed admission required')
    return dict(module_id=module_id, version=version, release_id=release_id, instance_token=token)
