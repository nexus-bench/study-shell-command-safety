"""Full-run gate: immutable evidence plus separately granted authorization."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

_VERIFIED = {}

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def check(worker, live=False):
    bundle=Path(__file__).resolve().parent
    base=bundle.parent
    auth=json.loads((base/'rerun-v3-launch-authorization.json').read_text())
    if auth.get('authorized') is not True:
        raise RuntimeError('BLOCKED: full-run authorization has not been granted')
    freeze=base/'rerun-v3-freeze.json'
    if auth.get('freezeSha256')!=digest(freeze):
        raise RuntimeError('BLOCKED: authorization does not match frozen artifacts')
    if worker not in ('worker-a','worker-b') or worker not in auth.get('workers',[]):
        raise RuntimeError('BLOCKED: worker is not authorized')
    cache_key=(auth['freezeSha256'],worker)
    # Root-owned artifacts are hidden from agents. Verify the complete archive
    # once per controller process, while checking authorization on every call.
    if not live and cache_key in _VERIFIED:
        return _VERIFIED[cache_key]
    frozen=json.loads(freeze.read_text())
    if not frozen.get('pilot'): raise RuntimeError('BLOCKED: pilot evidence missing')
    for name, expected in frozen['sha256'].items():
        path=(base/name).resolve()
        if not path.is_relative_to(base) or not path.is_file() or digest(path)!=expected:
            raise RuntimeError('BLOCKED: frozen artifact changed: '+name)
    # Recompute readiness; a copied status JSON is not a gate.
    import importlib.util
    spec=importlib.util.spec_from_file_location('prepared_freeze',base/'freeze_v3.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    readiness=module.verify(frozen)
    if readiness['errors'] or readiness['pending']:
        raise RuntimeError('BLOCKED: readiness requirements remain')
    if live:
        if os.geteuid()!=0: raise RuntimeError('VM root controller required')
        from runtime_fingerprint import fingerprint
        if digest(Path('/observer/enter-cgroup.py'))!=digest(bundle/'enter-cgroup.py'):
            raise RuntimeError('BLOCKED: installed cgroup helper drift')
        expected=json.loads((base/'rerun-v3-environment.json').read_text())['fingerprint']
        if fingerprint()!=expected: raise RuntimeError('BLOCKED: installed runtime drift')
        mounts=subprocess.run(['findmnt','-rn','-t','9p,virtiofs'],capture_output=True,text=True)
        if mounts.returncode not in (0,1) or mounts.stdout.strip():
            raise RuntimeError('BLOCKED: unexpected host mounts')
        memory=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemTotal:')))*1024
        if os.cpu_count()!=4 or not 3.5*1024**3 < memory < 4.5*1024**3:
            raise RuntimeError('BLOCKED: VM resource configuration differs from pilot')
    rows=[json.loads(x) for x in (base/f'rerun-v3-{worker}.jsonl').read_text().splitlines()]
    _VERIFIED[cache_key]=rows
    return rows
