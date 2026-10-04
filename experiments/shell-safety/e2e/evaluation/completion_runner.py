"""Execute an explicitly selected batch with frozen grading and subscription relays."""
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import broker
import study_runner as original
from claude_subscription_runner import subscription_headers

def main():
    assert os.geteuid() == 0
    ctypes.CDLL(None).prctl(4,0,0,0,0)
    request=json.load(sys.stdin)
    runid=request['runId']; provider=request['provider']; rows=request['rows']
    assert runid.replace('-','').isalnum() and provider in original.KEYS
    assert 0 < len(rows) <= 20 and all(r['provider']==provider for r in rows)
    with open('/observer/study.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for group in Path('/sys/fs/cgroup').glob('bench-*'):
            if 'populated 1' in (group/'cgroup.events').read_text():
                raise RuntimeError('Another episode is active')
        subprocess.run([sys.executable,str(original.ROOT/'launch_gate.py')],check=True)
        policy=json.loads((original.ROOT/'network-policy.json').read_text())
        subprocess.run(['nft','delete','table','inet','bench_agent'],capture_output=True)
        subprocess.run(['nft','-f','-'],input=policy['rules'],text=True,check=True)
        source=Path('/opt/bench/agent/linux-agent.mjs').read_text()
        if provider=='claude':
            needle="ANTHROPIC_API_KEY:'benchmark-placeholder'"
            assert source.count(needle)==1
            source=source.replace(needle,"CLAUDE_CODE_OAUTH_TOKEN:'benchmark-placeholder'")
            original.KEYS['claude']='CLAUDE_CODE_OAUTH_TOKEN'
            broker.ROUTES={'claude':('api.anthropic.com','',{'/v1/messages','/v1/messages/count_tokens'},'CLAUDE_CODE_OAUTH_TOKEN')}
        elif provider=='codex':
            assert source.count("model:'gpt-6-astra'")==1
            source=source.replace("model:'gpt-6-astra'","model:'gpt-6-sol'")
            broker.ROUTES={'codex':('chatgpt.com','/backend-api/codex',{'/responses','/responses/compact'},'OPENAI_API_KEY')}
        directory=Path('/var/lib/bench-completion'); directory.mkdir(mode=0o755,exist_ok=True)
        agent=directory/'linux-agent.mjs'; agent.write_text(source);agent.chmod(0o644)
        outer=original.outer_command
        original.outer_command=lambda world:[*outer(world),'--ro-bind',str(agent),'/opt/bench/agent/linux-agent.mjs']
        key=request['key']; keyname=original.KEYS[provider]
        connection_class=broker.http.client.HTTPSConnection
        class Connection(connection_class):
            def request(self,method,url,body=None,headers=None,**kwargs):
                if provider=='claude': headers=subscription_headers(headers,key)
                elif provider=='codex': headers={**(headers or {}),'ChatGPT-Account-Id':request['accountId']}
                return super().request(method,url,body,headers,**kwargs)
        broker.http=SimpleNamespace(client=SimpleNamespace(HTTPSConnection=Connection,HTTPException=broker.http.client.HTTPException))
        cases={r['id']:r for r in json.loads((original.ROOT/'cases.json').read_text())}
        planned={r['episodeId']:r for r in map(json.loads,(original.ROOT/'schedule.jsonl').read_text().splitlines())}
        output=Path('/observer/study-results')/runid;output.mkdir(mode=0o700,parents=True,exist_ok=True)
        for row in rows:
            base=planned[row['sourceEpisodeId']]
            assert all(row[k]==base[k] for k in ('provider','caseId','corpusSha256','repetition','section','variant'))
            assert row['episodeId']==row['sourceEpisodeId']+'-resume1'
            marker=output/(row['episodeId']+'.started')
            if marker.exists(): raise RuntimeError('Attempt already reserved; do not silently retry')
            if request.get('expiresAt',float('inf')) < time.time()+330:
                print(json.dumps({'batchStop':'credential-expiry'}),flush=True);return
            with marker.open('x') as f:json.dump(row,f);f.flush();os.fsync(f.fileno())
            result=original.run_episode(cases[row['caseId']],row,{keyname:key},output)
            if provider=='codex':
                result['requestedModel']='gpt-6-sol'
                result['effectivePolicy']={**result['effectivePolicy'],'model':'gpt-6-sol'}
            result['adapterSha256']=hashlib.sha256(agent.read_bytes()).hexdigest()
            original.save(output/(row['episodeId']+'.json'),result)
            print(json.dumps({'attempt':row['episodeId'],'terminalStatus':result['terminalStatus'],
                'taskCompleted':result.get('taskCompleted'),'gradingError':bool(result.get('gradingError')),
                'credentialLeakDetected':result.get('credentialLeakDetected')}),flush=True)
            if result['terminalStatus'] in ('runtime-error','service-error') or result.get('gradingError') or result.get('credentialLeakDetected'):
                print(json.dumps({'batchStop':'investigate-failed-attempt'}),flush=True);return

if __name__=='__main__': main()
