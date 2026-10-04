"""Run credential-free controls only; never starts an AI provider."""
import datetime
import json
from pathlib import Path
import subprocess
import uuid
from corpus import corpus_hash

here = Path(__file__).resolve().parent
name = 'shell-observer-controls-' + uuid.uuid4().hex[:12]
image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', 'shell-safety-e2e:observer-dev'], text=True).strip()
args = ['docker', 'run', '--rm', '--name', name, '--network=none', '--read-only',
        '--cap-drop=ALL', '--cap-add=SETUID', '--cap-add=SETGID', '--cap-add=CHOWN', '--cap-add=DAC_OVERRIDE',
        '--security-opt=no-new-privileges', '--pids-limit=128', '--memory=512m', '--cpus=2',
        '--tmpfs', '/world:rw,nosuid,size=64m', image]
try:
    p = subprocess.run(args, capture_output=True, text=True, timeout=120)
finally:
    subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
if p.returncode:
    raise SystemExit(p.stderr or p.stdout)
record = json.loads(p.stdout)
assert record['corpusSha256'] == corpus_hash(), 'Image contains a stale corpus; rebuild before running'
record['imageId'] = image
record['dockerArgs'] = args
record['recordedAt'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
out = here/'results'
out.mkdir(exist_ok=True)
path = out/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-controls.json')
path.write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps({'checksPassed': record['checksPassed'], 'providerRuns': 0,
                  'corpusSha256': record['corpusSha256'], 'record': str(path)}, indent=2))
