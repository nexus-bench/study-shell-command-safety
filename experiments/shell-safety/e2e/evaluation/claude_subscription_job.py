"""Explicitly launch the prepared Claude subscription pilot and separate collection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
JOB = ROOT/'study-results/claude-subscription-v1'
PILOT = 'claude-subscription-pilot-v1'
RUN = 'claude-subscription-v1'

def status(stage, **extra):
    JOB.mkdir(parents=True, exist_ok=True)
    path = JOB/'job-status.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'runId': RUN, 'stage': stage,
        'updatedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **extra}, indent=2)+'\n')
    tmp.replace(path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly resume: run four pilots then 360 Claude episodes")
    args = parser.parse_args()
    if not args.execute:
        parser.error("Benchmark remains stopped. Use --execute only when resumption is authorized.")
    prior = json.loads((ROOT/"study-results/study-v1/job-status.json").read_text())
    if prior.get("stage") not in ("stopped-by-user", "collection-finished", "needs-attention") or prior.get("archiveExitCode") != 0 or prior.get("vmStopExitCode") != 0:
        raise RuntimeError("Prior collection must be archived and VM stopped")
    # Read only the selected Claude Code credential. Never export refresh tokens.
    credential = subprocess.run(["security", "find-generic-password",
        "-s", "Claude Code-credentials", "-w"], capture_output=True, text=True, check=True)
    auth = json.loads(credential.stdout)["claudeAiOauth"]
    credential = None
    if auth.get("subscriptionType") not in ("pro", "max", "team", "enterprise") or "user:inference" not in auth.get("scopes", []):
        raise RuntimeError("A Claude subscription login with inference access is required")
    token = auth["accessToken"]
    expires = auth["expiresAt"]
    if expires <= (time.time()+600)*1000:
        raise RuntimeError("Refresh Claude login before resuming; subscription token expires soon")
    payload = json.dumps({"accessToken": token, "expiresAt": expires})
    auth = None
    env = {k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')}
    env['LIMA_HOME'] = str(Path.home()/'.cache/shell-bench-lima')
    cli = str(ROOT/'.runtime/bin/limactl')
    shell = [cli, 'shell', 'shell-bench-d13', '--']
    subprocess.run([sys.executable, str(ROOT/'vm.py'), 'start'], env=env, check=True)
    try:
        wrapper = (ROOT/'claude_subscription_runner.py').read_bytes()
        expected = json.loads((JOB/'amendment.json').read_text())['runnerSha256']
        if hashlib.sha256(wrapper).hexdigest() != expected:
            raise RuntimeError('Subscription runner changed after amendment was recorded')
        installer = 'import sys,pathlib; p=pathlib.Path("/observer/claude_subscription_runner.py"); p.write_bytes(sys.stdin.buffer.read()); p.chmod(0o600)'
        subprocess.run([*shell, 'sudo', 'python3', '-c', installer], input=wrapper, env=env, check=True)
        for runid, development in ((PILOT, True), (RUN, False)):
            status('piloting' if development else 'collecting', expectedEpisodes=4 if development else 360)
            command = [*shell, 'sudo', 'python3', '/observer/claude_subscription_runner.py', '--run-id', runid]
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
