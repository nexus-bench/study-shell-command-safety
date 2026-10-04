"""Resume authorized missing/error cases; preserve attempts, archive, and analyze."""
import argparse
import base64
import collections
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parent
JOB=ROOT/'study-results/study-completion-v1'
ENV={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')}
ENV['LIMA_HOME']=str(Path.home()/'.cache/shell-bench-lima')
SHELL=[str(ROOT/'.runtime/bin/limactl'),'shell','shell-bench-d13','--']

def save(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(path)

def auth(provider):
    if provider=='claude':
        def read():
            proc=subprocess.run(['security','find-generic-password','-s','Claude Code-credentials','-w'],capture_output=True,text=True,check=True)
            return json.loads(proc.stdout)['claudeAiOauth']
        data=read()
        if data['expiresAt']/1000 < time.time()+650:
            # Let the official CLI renew its own login; no tools, plugins or project context.
            with tempfile.TemporaryDirectory(prefix='bench-auth-') as directory:
                subprocess.run([str(Path.home()/'.local/bin/claude'),'-p','Reply OK.',
                    '--safe-mode','--tools','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
                    '--no-session-persistence','--model','claude-opus-5-5'],
                    cwd=directory,env=ENV,capture_output=True,text=True,timeout=120,check=True)
            data=read()
        if data.get('subscriptionType') not in ('pro','max','team','enterprise') or 'user:inference' not in data.get('scopes',[]):
            raise ValueError('Claude subscription login required')
        return {'key':data['accessToken'],'expiresAt':data['expiresAt']/1000}
    if provider=='codex':
        data=json.loads((Path.home()/'.codex/auth.json').read_text())
        if data.get('auth_mode')!='chatgpt':raise ValueError('ChatGPT login required')
        token=data['tokens']['access_token'];part=token.split('.')[1]
        expiry=json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))['exp']
        return {'key':token,'accountId':data['tokens']['account_id'],'expiresAt':expiry}
    name={'cursor':'CURSOR_API_KEY','qwen':'OPENROUTER_API_KEY'}[provider]
    for line in Path(__import__("os").environ["BENCH_CREDENTIALS_FILE"]).read_text().splitlines():
        if '=' not in line or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1)
        if key.strip().removeprefix('export ')==name:
            value=shlex.split(value,comments=True)
            if value and value[0]:return {'key':value[0]}
    raise ValueError('Missing selected provider key')

def prepare():
    JOB.mkdir(parents=True,exist_ok=True)
    schedule=[json.loads(x) for x in (ROOT/'schedule.jsonl').read_text().splitlines()]
    old=[json.loads(x) for x in (ROOT/'study-results/study-v1/results.jsonl').read_text().splitlines()]
    completed={r['episodeId'] for r in old if r['terminalStatus']=='completed' and not r.get('gradingError')}
    rows=[]
    for row in schedule:
        if row['provider']!='codex' and row['episodeId'] in completed:continue
        rows.append({**row,'sourceEpisodeId':row['episodeId'],'episodeId':row['episodeId']+'-resume1',
            'authenticationMode':{'claude':'claude-subscription','codex':'chatgpt-subscription'}.get(row['provider'],'api-key'),
            'configurationAmendment':'study-completion-v1'})
    manifest={'runId':'study-completion-v1','expectedAttempts':len(rows),'counts':dict(collections.Counter(r['provider'] for r in rows)),
        'rows':rows,'selection':'Preserve terminal-completed attempts for unchanged models, regardless of outcome; rerun missing/cancelled/runtime/service/timeout/grading errors. Replace all Astra attempts with Sol in primary comparison; preserve originals.',
        'billingCaveat':'Claude combines earlier API and later subscription attempts with authentication strata recorded. Codex primary is Sol subscription only. No authentication-route causal claims.',
        'retryPolicy':'One explicitly authorized new attempt for each selected episode. Stop a provider on service/runtime/grading/credential error; continue other providers. Do not retry new task failures to improve scores.',
        'semanticReview':'Two blinded independent reviewers plus adjudication remain required; missing labels remain null.',
        'runnerSha256':hashlib.sha256((ROOT/'completion_runner.py').read_bytes()).hexdigest()}
    path=JOB/'manifest.json'
    if path.exists():
        if json.loads(path.read_text())!=manifest:raise ValueError('Completion manifest changed')
    else:save(path,manifest)
    return manifest

def finalize(state):
    manifest=json.loads((JOB/'manifest.json').read_text())
    old=[json.loads(x) for x in (ROOT/'study-results/study-v1/results.jsonl').read_text().splitlines()]
    selected={r['episodeId']:{**r,'sourceRun':'study-v1','attemptId':r['episodeId'],
        'authenticationMode':r.get('authenticationMode','api-key')} for r in old
        if r['provider']!='codex' and r['terminalStatus']=='completed' and not r.get('gradingError')}
    for provider in manifest['counts']:
        runid='completion-'+provider+'-v1'
        path=ROOT/'study-results'/runid/'results.jsonl'
        if not path.exists():continue
        for line in path.read_text().splitlines():
            row=json.loads(line);eid=row['sourceEpisodeId']
            selected[eid]={**row,'episodeId':eid,'attemptId':row['episodeId'],'sourceRun':runid}
    schedule=[json.loads(x) for x in (ROOT/'schedule.jsonl').read_text().splitlines()]
    results=[selected[r['episodeId']] for r in schedule if r['episodeId'] in selected]
    (JOB/'results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in results))
    from analyze import summarize
    save(JOB/'preliminary-analysis.json',summarize(results,schedule))
    from review_packets import export
    destination=JOB/'semantic-review'
    if not destination.exists():export(results,json.loads((ROOT/'cases.json').read_text()),destination)
    state['recordedPrimaryEpisodes']=len(results)
    state['missingPrimaryEpisodes']=len(schedule)-len(results)
    state['semanticPending']=sum(r.get('semanticReviewRequired',False) for r in results)
    state['primaryTerminalStatuses']=dict(collections.Counter(r['terminalStatus'] for r in results))
    state['stage']='collected-pending-review' if len(results)==len(schedule) and not state['blockedProviders'] else 'needs-attention'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    manifest=prepare()
    if not args.execute:print(json.dumps({'expectedAttempts':manifest['expectedAttempts'],'counts':manifest['counts']}));return
    # Protect the host supervisor and its VM lifecycle from concurrent launches.
    import fcntl
    with (JOB/'supervisor.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=JOB/'job-status.json'
        if path.exists():raise ValueError('Existing completion attempt; inspect before resuming supervisor')
        state={'stage':'starting','completedAttempts':0,'expectedAttempts':manifest['expectedAttempts'],'blockedProviders':{},'attempts':[]}
        save(path,state)
        subprocess.run([sys.executable,str(ROOT/'vm.py'),'start'],env=ENV,check=True)
        queues={p:[r for r in manifest['rows'] if r['provider']==p] for p in ('claude','codex','cursor','qwen')}
        try:
            for filename in ('completion_runner.py','claude_subscription_runner.py'):
                data=(ROOT/filename).read_bytes()
                if filename=='completion_runner.py' and hashlib.sha256(data).hexdigest()!=manifest['runnerSha256']:raise ValueError('Runner hash mismatch')
                script='import sys,pathlib; p=pathlib.Path("/observer/'+filename+'"); p.write_bytes(sys.stdin.buffer.read()); p.chmod(0o600)'
                subprocess.run([*SHELL,'sudo','python3','-c',script],input=data,env=ENV,check=True)
            while any(queues.values()):
                for provider,queue in queues.items():
                    if not queue:continue
                    runid='completion-'+provider+'-v1'
                    state.update(stage='collecting',activeProvider=provider,remaining={p:len(q) for p,q in queues.items()})
                    save(path,state)
                    try:
                        credential=auth(provider)
                        available=credential.get('expiresAt',time.time()+7200)-time.time()-360
                        size=min(20,len(queue),int(available//320))
                        if size<1:raise ValueError('Subscription login needs renewal')
                        payload={**credential,'runId':runid,'provider':provider,'rows':queue[:size]}
                        proc=subprocess.Popen([*SHELL,'sudo','python3','/observer/completion_runner.py'],env=ENV,
                            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                        proc.stdin.write(json.dumps(payload));proc.stdin.close()
                        stop=None;finished=[]
                        for line in proc.stdout:
                            line=line.replace(credential['key'],'[REDACTED]')
                            print(line,end='',flush=True)
                            try:event=json.loads(line)
                            except ValueError:continue
                            if 'attempt' in event:
                                finished.append(event['attempt']);state['attempts'].append(event)
                                state['completedAttempts']+=1;save(path,state)
                            if 'batchStop' in event:stop=event['batchStop']
                        code=proc.wait()
                        queue[:]=[r for r in queue if r['episodeId'] not in finished]
                        if code or (stop and stop!='credential-expiry') or not finished:
                            raise RuntimeError(stop or 'Batch execution failed')
                    except Exception as error:
                        state['blockedProviders'][provider]={'errorType':type(error).__name__,'remaining':len(queue)}
                        queue.clear();save(path,state)
        finally:
            state['stage']='archiving';save(path,state)
            for provider in queues:
                runid='completion-'+provider+'-v1'
                result=subprocess.run([sys.executable,str(ROOT/'collect-study.py'),runid],env=ENV,capture_output=True,text=True)
                state.setdefault('archiveExitCodes',{})[provider]=result.returncode
            result=subprocess.run([sys.executable,str(ROOT/'vm.py'),'stop'],env=ENV)
            state['vmStopExitCode']=result.returncode
            finalize(state);save(path,state)

if __name__=='__main__': main()
