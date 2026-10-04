"""Codex-only subscription amendment; Sol model override, unchanged grading."""
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
import broker
import study_runner as original

MODEL = 'gpt-6-sol'

def prepare_agent():
    source = Path('/opt/bench/agent/linux-agent.mjs').read_text()
    needle = "model:'gpt-6-astra'"
    if source.count(needle) != 1:
        raise ValueError('Expected exactly one frozen Codex model selection')
    directory = Path('/var/lib/bench-subscription')
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    agent = directory/'linux-agent.mjs'
    agent.write_text(source.replace(needle, "model:'"+MODEL+"'"))
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
    token, account = request['accessToken'], request['accountId']
    if not token or not account:
        raise ValueError('Missing subscription credentials')
    lock = open('/observer/study.lock', 'w')
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
    broker.ROUTES = {'codex': ('chatgpt.com', '/backend-api/codex',
                             {'/responses', '/responses/compact'}, 'OPENAI_API_KEY')}
    connection_class = broker.http.client.HTTPSConnection
    class SubscriptionConnection(connection_class):
        def request(self, method, url, body=None, headers=None, **kwargs):
            headers = dict(headers or {})
            headers['ChatGPT-Account-Id'] = account
            return super().request(method, url, body, headers, **kwargs)
    broker.http = SimpleNamespace(client=SimpleNamespace(HTTPSConnection=SubscriptionConnection,
            HTTPException=broker.http.client.HTTPException))
    if args.development:
        cases = json.loads((original.ROOT/'development-cases.json').read_text())
        schedule = [{'episodeId': 'codex-'+r['id'], 'caseId': r['id'],
                     'provider': 'codex', 'corpusSha256': 'development'} for r in cases]
    else:
        cases = json.loads((original.ROOT/'cases.json').read_text())
        schedule = [json.loads(x) for x in (original.ROOT/'schedule.jsonl').read_text().splitlines()]
        schedule = [r for r in schedule if r['provider'] == 'codex']
        assert len(schedule) == 360
    cases = {r['id']: r for r in cases}
    output = Path('/observer/study-results')/args.run_id
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    for row in schedule:
        row = {**row, 'authenticationMode': 'chatgpt-subscription',
               'configurationAmendment': 'codex-subscription-v1'}
        marker = output/(row['episodeId']+'.started')
        if marker.exists():
            continue
        with marker.open('x') as f:
            json.dump(row, f); f.flush(); os.fsync(f.fileno())
        result = original.run_episode(cases[row['caseId']], row,
                                      {'OPENAI_API_KEY': token}, output)
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
