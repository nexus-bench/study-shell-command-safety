"""Deploy credential-free candidate to its own VM directory and run tests only."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'USER', 'TMPDIR', 'LANG')}
env['LIMA_HOME'] = str(Path.home() / '.cache/shell-bench-lima')
cli = str(root / '.runtime/bin/limactl')
vm = 'shell-bench-d13'
def shell(*args, **kw):
    return subprocess.run([cli, 'shell', vm, '--', *args], env=env, **kw)

shell('sudo', 'mkdir', '-p', '/observer/rerun-v3-opaque-smoke', check=True)
subprocess.run([cli, 'copy', str(root / 'rerun-v3-opaque-smoke'), vm + ':/home/benchadmin/'], env=env, check=True)
shell('sudo', 'cp', '-R', '/home/benchadmin/rerun-v3-opaque-smoke/.', '/observer/rerun-v3-opaque-smoke/', check=True)
shell('sudo', 'chmod', '700', '/observer/rerun-v3-opaque-smoke', check=True)
result = shell('sudo', 'python3', '/observer/rerun-v3-opaque-smoke/test_v2_vm.py', '-v', text=True, capture_output=True)
report = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
          'providerEpisodesRun': 0, 'fullEvaluationStarted': False}
(root / 'rerun-v3-opaque-smoke-vm-prechecks.json').write_text(json.dumps(report, indent=2) + '\n')
print(result.stdout); print(result.stderr)
sys.exit(result.returncode)
