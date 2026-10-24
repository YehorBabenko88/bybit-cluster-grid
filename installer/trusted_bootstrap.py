"""Offline LS5 executable provenance verifier. No filesystem, process or host I/O.

Claims are synthetic and cannot authorize physical execution. The policy is only
a candidate inventory: independent authenticated provenance remains mandatory.
"""
import hashlib
import json
import ntpath
import re

MAX_BYTES = 1_048_576
SHA = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
VERSION = "9ab1f5b85ec471ea21ec89f1b76740c0b01537b6"
DENY_ENV = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE",
            "PYTHONINSPECT", "PYTHONBREAKPOINT", "PYTHONWARNINGS",
            "PYTHONPYCACHEPREFIX", "PYTHONSAFEPATH", "PYTHONNOUSERSITE")


def pairs_unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[k] = v
    return result


def decode(raw):
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_BYTES:
        raise ValueError("INVALID_SIZE")
    def nonfinite(_):
        raise ValueError("NONFINITE_JSON")
    return json.loads(raw, object_pairs_hook=pairs_unique, parse_constant=nonfinite)


def path(value):
    if type(value) is not str or not 4 <= len(value) <= 240:
        raise ValueError("INVALID_PATH")
    if not re.fullmatch(r"[A-Z]:\\[A-Za-z0-9_.\\-]+", value):
        raise ValueError("INVALID_PATH")
    parts = value[3:].split("\\")
    if any(not x or x in (".", "..") or x.endswith(".") or
           x.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL",
           *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))}
           for x in parts):
        raise ValueError("PATH_ALIAS")
    return value.casefold()


def under(value, root):
    return value == root or value.startswith(root + "\\")


def exact(obj, names):
    if type(obj) is not dict or set(obj) != set(names.split()):
        raise ValueError("INVALID_FIELDS")


def assess(policy_raw, observation_raw):
    result = dict(schema="grid-ls5-bootstrap-model-1", status="BLOCKED",
                  model_status="BLOCKED", host_verified=False,
                  execute_authorized=False, cleanup_authorized=False,
                  deployment_authorized=False, physical_tests="0/10 NOT_RUN",
                  findings=[], policy_sha256=None, observation_sha256=None)
    try:
        p, o = decode(policy_raw), decode(observation_raw)
        result["policy_sha256"] = hashlib.sha256(policy_raw.encode()).hexdigest()
        result["observation_sha256"] = hashlib.sha256(observation_raw.encode()).hexdigest()
        exact(p, "schema head active_release trusted_root executable_root inventory")
        exact(o, "schema head active_release trusted_root executable_root files runtime environment custody tasks")
        if p["schema"] != "grid-ls5-bootstrap-policy-1" or o["schema"] != "grid-ls5-bootstrap-observation-1":
            raise ValueError("SCHEMA")
        if type(p["head"]) is not str or not COMMIT.fullmatch(p["head"]) or o["head"] != p["head"]:
            raise ValueError("HEAD")
        if p["active_release"] != VERSION or o["active_release"] != VERSION:
            raise ValueError("ACTIVE_RELEASE")
        trust = path(p["trusted_root"])
        executable = path(p["executable_root"])
        if trust == executable or under(trust, executable) or under(executable, trust):
            raise ValueError("TRUST_ROOT_OVERLAP")
        if path(o["trusted_root"]) != trust or path(o["executable_root"]) != executable:
            raise ValueError("ROOT_DRIFT")
        inv = p["inventory"]
        if type(inv) is not dict or not 1 <= len(inv) <= 8192:
            raise ValueError("INVENTORY")
        normalized = {}
        for filename, digest in inv.items():
            normalized_name = path(filename)
            if normalized_name in normalized or not under(normalized_name, executable):
                raise ValueError("INVENTORY_ALIAS_OR_SCOPE")
            if type(digest) is not str or not SHA.fullmatch(digest):
                raise ValueError("DIGEST")
            normalized[normalized_name] = digest
        # Minimum critical executable inputs; this does not prove transitive closure.
        mandatory = (
            executable + "\\runtime\\python.exe",
            executable + "\\runtime\\pyvenv.cfg",
            executable + "\\runtime\\python311.dll",
            executable + "\\runtime\\site-packages\\sitecustomize.py",
            executable + "\\runtime\\site-packages\\grid.pth",
            executable + "\\releases\\" + VERSION + "\\grid\\coordinator.py",
            executable + "\\installer\\coordinator-launcher.ps1",
        )
        if not set(mandatory).issubset(normalized):
            raise ValueError("MANDATORY_EXECUTABLE_INPUT_MISSING")
        if type(o["files"]) is not list or len(o["files"]) != len(normalized):
            raise ValueError("FILE_SET")
        seen = set()
        for entry in o["files"]:
            exact(entry, "path sha256 kind owner_trusted acl_custody_trusted ancestors_trusted reparse hardlinks")
            name = path(entry["path"])
            if name in seen or name not in normalized or entry["sha256"] != normalized[name]:
                raise ValueError("FILE_MISMATCH")
            seen.add(name)
            if entry["kind"] != "FILE" or any(entry[k] is not True for k in
                    ("owner_trusted", "acl_custody_trusted", "ancestors_trusted")):
                raise ValueError("UNTRUSTED_FILE")
            if entry["reparse"] is not False or type(entry["hardlinks"]) is not int or entry["hardlinks"] != 1:
                raise ValueError("LINK_RISK")
        if seen != set(normalized):
            raise ValueError("INCOMPLETE_FILES")
        runtime = o["runtime"]
        exact(runtime, "python_exe pyvenv_cfg site_packages dll_search_paths imports_closed")
        required_runtime = {
            "python_exe": executable + "\\runtime\\python.exe",
            "pyvenv_cfg": executable + "\\runtime\\pyvenv.cfg",
            "site_packages": executable + "\\runtime\\site-packages\\sitecustomize.py",
        }
        for name, expected in required_runtime.items():
            if path(runtime[name]) != expected or expected not in normalized:
                raise ValueError("RUNTIME_NOT_PINNED")
        if runtime["imports_closed"] is not True:
            raise ValueError("IMPORT_CLOSURE_UNKNOWN")
        if type(runtime["dll_search_paths"]) is not list or not runtime["dll_search_paths"]:
            raise ValueError("DLL_PATHS_UNKNOWN")
        for d in runtime["dll_search_paths"]:
            # A trusted root alone is not a pinned executable closure.
            if not under(path(d), executable):
                raise ValueError("DLL_PATH_UNTRUSTED")
        env = o["environment"]
        exact(env, "variables path_entries cwd_trusted user_site_disabled isolated_python")
        if type(env["variables"]) is not dict or any(type(k) is not str or type(v) is not str or k.upper() in DENY_ENV for k,v in env["variables"].items()):
            raise ValueError("PYTHON_ENV_POISONED")
        if len({k.upper() for k in env["variables"]}) != len(env["variables"]):
            raise ValueError("ENV_CASE_ALIAS")
        if any(k.upper() in ("PSMODULEPATH", "COMSPEC", "PATHEXT", "VIRTUAL_ENV", "PYTHONIOENCODING") for k in env["variables"]):
            raise ValueError("LOADER_ENV_UNCLASSIFIED")
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) or
               "\x00" in v or "\r" in v or "\n" in v for k, v in env["variables"].items()):
            raise ValueError("ENV_NAME_OR_VALUE_INVALID")
        if type(env["path_entries"]) is not list or not env["path_entries"]:
            raise ValueError("PATH_UNKNOWN")
        if any(not under(path(d), executable)
               for d in env["path_entries"]):
            raise ValueError("PATH_POISONED")
        if env["cwd_trusted"] is not True or env["user_site_disabled"] is not True or env["isolated_python"] is not True:
            raise ValueError("PYTHON_ISOLATION_UNKNOWN")
        custody = o["custody"]
        exact(custody, "source_independently_authenticated no_preexisting_writers handles_stable after_acl_rebuild fresh_rebuilt_runtime")
        if any(v is not True for v in custody.values()):
            raise ValueError("CUSTODY_UNPROVEN")
        tasks = o["tasks"]
        exact(tasks, "grid_disabled unrelated_tasks_classified recovery_disabled")
        if any(v is not True for v in tasks.values()):
            raise ValueError("TASKS_UNVERIFIED")
        result["model_status"] = "OFFLINE_MODEL_PASS"
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError) as e:
        result["findings"].append(str(e)[:80] or "INVALID_CONTRACT")
        result["model_status"] = "FAIL"
    return result
