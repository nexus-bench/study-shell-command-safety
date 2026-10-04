"""Claude subscription amendment; unchanged Opus model and grading."""
import argparse
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import time
import broker
import study_runner as original

MODEL = 'claude-opus-5-5'

def subscription_headers(headers, token):
    # The SDK sees only a placeholder; the root relay owns the actual token.
    headers = {k: v for k, v in (headers or {}).items()
               if k.lower() not in ("x-api-key", "authorization")}
    headers["Authorization"] = "Bearer "+token
    beta_key = next((k for k in headers if k.lower()=="anthropic-beta"), "anthropic-beta")
    betas = [v.strip() for v in headers.get(beta_key, "").split(",") if v.strip()]
    if "oauth-2025-04-20" not in betas:
        betas.append("oauth-2025-04-20")
    headers[beta_key] = ",".join(betas)
    return headers

def prepare_agent():
    source = Path('/opt/bench/agent/linux-agent.mjs').read_text()
    needle = "ANTHROPIC_API_KEY:'benchmark-placeholder'"
    if source.count(needle) != 1:
        raise ValueError("Expected exactly one frozen Claude credential selection")
    directory = Path("/var/lib/bench-claude-subscription")
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    agent = directory/"linux-agent.mjs"
    agent.write_text(source.replace(needle, "CLAUDE_CODE_OAUTH_TOKEN:'benchmark-placeholder'"))
    agent.chmod(0o644)
    return agent

def main():
    assert os.geteuid() == 0
    ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)
    parser = argparse.ArgumentParser()
    parser.add_argument('--development', action='store_true')
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if not args.run_id.replace('-', '').isalnum():
        raise ValueError('Invalid run ID')
    request = json.load(sys.stdin)
    token, expires = request['accessToken'], request['expiresAt']
    if not token or expires <= time.time()*1000:
        raise ValueError('Missing subscription credentials')
    with open('/observer/study.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for group in Path('/sys/fs/cgroup').glob('bench-*'):
            if 'populated 1' in (group/'cgroup.events').read_text():
                raise RuntimeError('Another benchmark episode is active')
        subprocess.run([sys.executable, str(original.ROOT/'launch_gate.py')], check=True)
        agent = prepare_agent()
        outer_command = original.outer_command
        original.outer_command = lambda world: [*outer_command(world), '--ro-bind',
                                                str(agent), '/opt/bench/agent/linux-agent.mjs']
        policy = json.loads((original.ROOT/'network-policy.json').read_text())
        subprocess.run(['nft', 'delete', 'table', 'inet', 'bench_agent'], capture_output=True)
        subprocess.run(['nft', '-f', '-'], input=policy['rules'], text=True, check=True)
        # Keep the real OAuth token in the privileged relay, outside agent tools.
        original.KEYS = {**original.KEYS, "claude": "CLAUDE_CODE_OAUTH_TOKEN"}
        broker.ROUTES = {"claude": ("api.anthropic.com", "",
            {"/v1/messages", "/v1/messages/count_tokens"}, "CLAUDE_CODE_OAUTH_TOKEN")}
        connection_class = broker.http.client.HTTPSConnection
        class SubscriptionConnection(connection_class):
            def request(self, method, url, body=None, headers=None, **kwargs):
                headers = subscription_headers(headers, token)
                return super().request(method, url, body, headers, **kwargs)
        broker.http = SimpleNamespace(client=SimpleNamespace(HTTPSConnection=SubscriptionConnection,
            HTTPException=broker.http.client.HTTPException))
        if args.development:
            cases = json.loads((original.ROOT/'development-cases.json').read_text())
            schedule = [{'episodeId': 'claude-'+r['id'], 'caseId': r['id'],
                         'provider': 'claude', 'corpusSha256': 'development'} for r in cases]
        else:
            cases = json.loads((original.ROOT/'cases.json').read_text())
            schedule = [json.loads(x) for x in (original.ROOT/'schedule.jsonl').read_text().splitlines()]
            schedule = [r for r in schedule if r['provider'] == 'claude']
            assert len(schedule) == 360
        cases = {r['id']: r for r in cases}
        output = Path('/observer/study-results')/args.run_id
        output.mkdir(mode=0o700, parents=True, exist_ok=True)
        for row in schedule:
            row = {**row, 'authenticationMode': 'claude-subscription',
                   'configurationAmendment': 'claude-subscription-v1'}
            marker = output/(row['episodeId']+'.started')
            if marker.exists():
                if args.development:
                    prior = output/(row["episodeId"]+".json")
                    if not prior.exists() or json.loads(prior.read_text()).get("taskCompleted") is not True:
                        raise SystemExit("Previous pilot incomplete or failed; explicit new attempt required")
                continue
            if expires <= (time.time()+330)*1000:
                raise SystemExit("Subscription token needs refresh; no new episode started")
            with marker.open('x') as f:
                json.dump(row, f); f.flush(); os.fsync(f.fileno())
            result = original.run_episode(cases[row['caseId']], row,
                                          {'CLAUDE_CODE_OAUTH_TOKEN': token}, output)
            result['requestedModel'] = MODEL
            result['effectivePolicy'] = {**(result.get('effectivePolicy') or {}), 'model': MODEL}
            result['adapterSha256'] = hashlib.sha256(agent.read_bytes()).hexdigest()
            original.save(output/(row['episodeId']+'.json'), result)
            print(json.dumps({k: result.get(k) for k in (
                'episodeId', 'taskCompleted', 'terminalStatus', 'gradingError',
                'credentialLeakDetected', 'authenticationMode')}), flush=True)
            # Fail closed on service/auth/transport problems; never burn through quota failures.
            if result['terminalStatus'] in ('runtime-error', 'service-error') or result.get('gradingError') or result.get('credentialLeakDetected'):
                raise SystemExit('Stopped for investigation; attempted episode preserved')
            if args.development and result.get('taskCompleted') is not True:
                raise SystemExit('Subscription pilot did not pass; full rerun not started')

if __name__ == '__main__':
    main()
