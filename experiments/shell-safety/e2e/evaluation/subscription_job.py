"""Run the authorized Codex replacement after the existing collection releases its VM."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
JOB = ROOT/'study-results/codex-subscription-v1'
PILOT = 'codex-subscription-pilot-v1'
RUN = 'codex-subscription-v1'

def status(stage, **extra):
    JOB.mkdir(parents=True, exist_ok=True)
    path = JOB/'job-status.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'runId': RUN, 'stage': stage,
        'updatedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **extra}, indent=2)+'\n')
    tmp.replace(path)

def main():
    status('queued', waitingFor='study-v1 VM shutdown', expectedEpisodes=360)
    deadline = time.monotonic()+24*3600
    prior = ROOT/'study-results/study-v1/job-status.json'
    while True:
        state = json.loads(prior.read_text())
        if state['stage'] in ('collection-finished', 'needs-attention'):
            if state.get('archiveExitCode') != 0 or state.get('vmStopExitCode') != 0:
                raise RuntimeError('Prior collection did not archive and release the VM cleanly')
            break
        if time.monotonic() > deadline:
            raise RuntimeError('Prior collection did not finish within 24 hours')
        time.sleep(15)
    # Only read the specifically authorized Codex login; never export refresh tokens.
    auth = json.loads((Path.home()/'.codex/auth.json').read_text())
    if auth.get('auth_mode') != 'chatgpt':
        raise RuntimeError('Codex must be signed in with ChatGPT')
    tokens = auth['tokens']
    token = tokens['access_token']
    segment = token.split('.')[1]
    claims = json.loads(base64.urlsafe_b64decode(segment+'='*(-len(segment)%4)))
    if claims['exp'] < time.time()+8*3600:
        raise RuntimeError('Subscription token has less than eight hours left; refresh login before resuming')
    payload = json.dumps({'accessToken': token, 'accountId': tokens['account_id']})
    env = {k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')}
    env['LIMA_HOME'] = str(Path.home()/'.cache/shell-bench-lima')
    cli = str(ROOT/'.runtime/bin/limactl')
    shell = [cli, 'shell', 'shell-bench-d13', '--']
    subprocess.run([sys.executable, str(ROOT/'vm.py'), 'start'], env=env, check=True)
    try:
        wrapper = (ROOT/'subscription_runner.py').read_bytes()
        expected = json.loads((JOB/'amendment.json').read_text())['runnerSha256']
        if hashlib.sha256(wrapper).hexdigest() != expected:
            raise RuntimeError('Subscription runner changed after amendment was recorded')
        installer = 'import sys,pathlib; p=pathlib.Path("/observer/subscription_runner.py"); p.write_bytes(sys.stdin.buffer.read()); p.chmod(0o600)'
        subprocess.run([*shell, 'sudo', 'python3', '-c', installer], input=wrapper, env=env, check=True)
        for runid, development in ((PILOT, True), (RUN, False)):
            status('piloting' if development else 'collecting', expectedEpisodes=4 if development else 360)
            command = [*shell, 'sudo', 'python3', '/observer/subscription_runner.py', '--run-id', runid]
            if development:
                command.append('--development')
            proc = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            proc.stdin.write(payload); proc.stdin.close()
            for line in proc.stdout:
                print(line.replace(token, '[REDACTED]'), end='', flush=True)
            code = proc.wait()
            subprocess.run([sys.executable, str(ROOT/'collect-study.py'), runid], env=env, check=True)
            if code:
                raise RuntimeError('Subscription execution stopped; artifacts preserved in '+runid)
        with (JOB/'preliminary-analysis.json').open('w') as f:
            subprocess.run([sys.executable, str(ROOT/'analyze.py'), str(JOB/'results.jsonl')], stdout=f, check=True)
        subprocess.run([sys.executable, str(ROOT/'review_packets.py'), str(JOB/'results.jsonl'),
                        str(JOB/'semantic-review')], check=True)
    finally:
        subprocess.run([sys.executable, str(ROOT/'vm.py'), 'stop'], env=env, check=True)
    status('collection-finished', expectedEpisodes=360, semanticReviewPending=True)

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # No exception object from a credential-carrying request is printed.
        status('needs-attention', errorType=type(error).__name__,
               note='Review the redacted collection log; no failed episode was retried.')
        raise SystemExit(1)
