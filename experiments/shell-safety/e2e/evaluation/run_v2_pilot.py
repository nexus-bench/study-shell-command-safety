"""Run only the explicitly authorized 84-episode development pilot, then stop VM."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT / 'rerun-v2'
ENV = {k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')}
ENV['LIMA_HOME'] = str(Path.home() / '.cache/shell-bench-lima')
CLI = str(ROOT / '.runtime/bin/limactl')
VM = 'shell-bench-d13'

def shell(*args, **kw):
    return subprocess.run([CLI, 'shell', VM, '--', *args], env=ENV, **kw)

def main():
    prechecks = json.loads((ROOT / 'rerun-v2-vm-prechecks.json').read_text())
    if prechecks['returncode'] != 0:
        raise SystemExit('VM prechecks must pass first')
    run_id = 'v2-pilot-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    out = ROOT / 'study-results' / run_id
    out.mkdir(exist_ok=False)
    keys = {}
    status = {'runId': run_id, 'expected': 84, 'fullEvaluationStarted': False}
    try:
        # Read-only installed-adapter comparison before any credentials are read.
        got = shell('sudo','sha256sum','/opt/bench/agent/linux-agent.mjs',capture_output=True,text=True,check=True).stdout.split()[0]
        expected = hashlib.sha256((BUNDLE / 'linux-agent.mjs').read_bytes()).hexdigest()
        if got != expected:
            raise RuntimeError('Installed adapter differs from candidate')
        mounts = shell('findmnt','-rn','-t','9p,virtiofs',capture_output=True,text=True)
        if mounts.returncode not in (0,1) or mounts.stdout.strip():
            raise RuntimeError('Unexpected mount inventory or host mounts')
        fingerprint = shell('sudo','python3','/observer/rerun-v2/runtime_fingerprint.py',capture_output=True,text=True,check=True).stdout
        (out / 'runtime-fingerprint.json').write_text(fingerprint)
        network = shell('sudo','python3','/observer/rerun-v2/network_guard.py',capture_output=True,text=True,check=True).stdout
        (out / 'network-policy.json').write_text(network)
        subprocess.run([CLI,'copy',str(out/'runtime-fingerprint.json'),VM+':/home/benchadmin/v2-runtime-fingerprint.json'],env=ENV,check=True)
        shell('sudo','cp','/home/benchadmin/v2-runtime-fingerprint.json','/observer/rerun-v2/runtime-fingerprint.json',check=True)
        values = {}
        for line in Path(__import__("os").environ["BENCH_CREDENTIALS_FILE"]).read_text().splitlines():
            if '=' not in line or line.lstrip().startswith('#'):
                continue
            k,v = line.split('=',1); parts = shlex.split(v,comments=True)
            values[k.strip().removeprefix('export ')] = parts[0] if parts else ''
        names = ('ANTHROPIC_API_KEY','OPENAI_API_KEY','CURSOR_API_KEY','OPENROUTER_API_KEY')
        keys = {k:values.get(k,'') for k in names}
        if not all(keys.values()):
            raise RuntimeError('Missing provider credential')
        command = [CLI,'shell',VM,'--','sudo','python3','/observer/rerun-v2/study_runner.py',
                   '--development','--run-id',run_id,'--limit','84']
        proc = subprocess.Popen(command,env=ENV,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        proc.stdin.write(json.dumps({'keys':keys})); proc.stdin.close()
        with (out/'collection.log').open('w') as log:
            for line in proc.stdout:
                for secret in keys.values():
                    line = line.replace(secret,'[REDACTED]')
                log.write(line); log.flush(); print(line,end='',flush=True)
        status['returncode'] = proc.wait()
    except Exception as exc:
        status['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        # Archive controller evidence directly; do not expose root files to agent UID.
        with (out/'vm-artifacts.tar').open('wb') as archive:
            collected = shell('sudo','tar','-C','/observer/study-results','-cf','-',run_id,stdout=archive,stderr=subprocess.PIPE)
        status['archiveReturncode'] = collected.returncode
        stopped = subprocess.run([CLI,'stop',VM],env=ENV,capture_output=True,text=True)
        status['shutdownReturncode'] = stopped.returncode
        status['shutdownOutput'] = stopped.stdout + stopped.stderr
        text = json.dumps(status,indent=2)
        for secret in keys.values():
            if secret: text = text.replace(secret,'[REDACTED]')
        (out/'job-status.json').write_text(text+'\n')
        print(text,flush=True)
    if status.get('returncode') != 0 or status.get('error'):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
