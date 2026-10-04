"""Two isolated VM workers; disjoint reservations and no automatic retries."""
import argparse
import collections
import concurrent.futures
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import resume_study_v2 as previous
previous.JOB=previous.ROOT/"study-results/study-completion-v3"
REPLACE_EPISODE="stress-setup-guide-injected--r3--cursor"

ROOT=previous.ROOT
JOB=ROOT/'study-results/study-completion-v4'
VMS=('shell-bench-d13','shell-bench-d13-worker2')
CLI=str(ROOT/'.runtime/bin/limactl')
ENV=previous.ENV
save=previous.save

def shell(vm): return [CLI,'shell',vm,'--']

def prepare():
    prior=json.loads((previous.JOB/'job-status.json').read_text())
    if prior['stage'] not in ('needs-attention','collected-pending-review') or (set(prior.get('vmStopExitCodes',{}))!=set(VMS) or any(prior['vmStopExitCodes'].values())):
        raise ValueError('Serial collection must finish archiving and stop first')
    if not all(v==0 for v in prior['archiveExitCodes'].values()): raise ValueError('Archive incomplete')
    baseline=[json.loads(x) for x in (previous.JOB/'results.jsonl').read_text().splitlines()]
    replacement=next(r for r in baseline if r['episodeId']==REPLACE_EPISODE)
    assert replacement['terminalStatus']=='runtime-error' and replacement['terminal']['failure']=='Network request failed'
    baseline=[r for r in baseline if r['episodeId']!=REPLACE_EPISODE]
    present={r['episodeId'] for r in baseline}
    schedule=[json.loads(x) for x in (ROOT/'schedule.jsonl').read_text().splitlines()]
    rows=[{**r,'sourceEpisodeId':r['episodeId'],'episodeId':r['episodeId']+'-resume4',
        'authenticationMode':{'claude':'claude-subscription','codex':'chatgpt-subscription'}.get(r['provider'],'api-key'),
        'configurationAmendment':'study-completion-v4','osStratum':'debian13-updated-20261003'}
        for r in schedule if r['episodeId'] not in present]
    assert len(present)==len(baseline) and len(rows)+len(baseline)==len(schedule)==1440
    assert not present.intersection(r['sourceEpisodeId'] for r in rows)
    manifest={'runId':'study-completion-v4','preservedPrimaryEpisodes':len(baseline),
        'baselineSha256':hashlib.sha256((previous.JOB/'results.jsonl').read_bytes()).hexdigest(),
        'expectedAttempts':len(rows),'counts':dict(collections.Counter(r['provider'] for r in rows)),
        'authorizedReplacement':REPLACE_EPISODE,'previousAttemptRetainedIn':'study-completion-v3',
        'rows':sorted(rows,key=lambda r:r['sourceEpisodeId']!=REPLACE_EPISODE),'vms':list(VMS),'concurrency':2,
        'resources':{'vmCpus':4,'vmMemoryGiB':4,'episodeCpuQuota':2,'episodeMemoryGiB':3,'wallSeconds':300},
        'comparability':'Parallel operational stratum: VM memory reduced from 8 to 4 GiB, with unchanged episode cgroup limits. Record worker identity; do not interpret elapsed-time differences as model effects.',
        'policy':'One active batch per VM and per provider. Atomically claim disjoint cases. Preserve every earlier attempt; never retry reserved cases automatically.',
        'runnerSha256':hashlib.sha256((ROOT/'completion_runner_v4.py').read_bytes()).hexdigest()}
    JOB.mkdir(exist_ok=True,parents=True)
    path=JOB/'manifest.json'
    if path.exists() and json.loads(path.read_text())!=manifest: raise ValueError('Manifest changed')
    if not path.exists(): save(path,manifest)
    return manifest

def finalize(state,manifest):
    baseline=previous.JOB/'results.jsonl'
    assert hashlib.sha256(baseline.read_bytes()).hexdigest()==manifest['baselineSha256']
    selected={r['episodeId']:r for r in map(json.loads,baseline.read_text().splitlines()) if r['episodeId']!=REPLACE_EPISODE}
    for runid in state['runs']:
        path=ROOT/'study-results'/runid/'results.jsonl'
        if not path.exists():continue
        for row in map(json.loads,path.read_text().splitlines()):
            eid=row['sourceEpisodeId']
            if eid in selected:raise ValueError('Duplicate primary episode')
            selected[eid]={**row,'episodeId':eid,'attemptId':row['episodeId'],'sourceRun':runid}
    schedule=list(map(json.loads,(ROOT/'schedule.jsonl').read_text().splitlines()))
    results=[selected[r['episodeId']] for r in schedule if r['episodeId'] in selected]
    (JOB/'results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in results))
    from analyze import summarize
    save(JOB/'preliminary-analysis.json',summarize(results,schedule))
    strata={}
    for label in ('debian13-original','debian13-updated-20261003'):
        subset=[r for r in results if r.get('osStratum')==label]; ids={r['episodeId'] for r in subset}
        strata[label]=summarize(subset,[r for r in schedule if r['episodeId'] in ids])
    save(JOB/'os-stratified-analysis.json',{'limitation':'Descriptive only; case composition differs by OS stratum. Worker identity is recorded for parallel attempts.','strata':strata})
    from review_packets import export
    if not (JOB/'semantic-review').exists(): export(results,json.loads((ROOT/'cases.json').read_text()),JOB/'semantic-review')
    state.update(recordedPrimaryEpisodes=len(results),missingPrimaryEpisodes=1440-len(results),
        semanticPending=sum(bool(r.get('semanticReviewRequired')) for r in results))
    state['stage']='collected-pending-review' if len(results)==1440 and not state['blockedProviders'] and all(v==0 for v in state['archiveExitCodes'].values()) and all(v==0 for v in state['vmStopExitCodes'].values()) else 'needs-attention'

def execute(manifest):
    with (JOB/'supervisor.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=JOB/'job-status.json'
        if path.exists():raise ValueError('Existing run: inspect before any restart')
        state={'stage':'starting','completedAttempts':0,'expectedAttempts':manifest['expectedAttempts'],
            'preservedPrimaryEpisodes':manifest['preservedPrimaryEpisodes'],'attempts':[],
            'blockedProviders':{},'workers':{},'runs':{},'archiveExitCodes':{},'vmStopExitCodes':{}}
        mutex=threading.Lock(); credential_lock=threading.Lock()
        queues={p:[r for r in manifest['rows'] if r['provider']==p] for p in ('cursor','codex','claude','qwen')}
        owners=set(); order=list(queues)
        def persist():
            state['remaining']={p:len(q) for p,q in queues.items()};save(path,state)
        persist()
        # Both prevalidated VMs must be running before starting any attempts.
        for vm in VMS:
            subprocess.run([*shell(vm),'sudo','python3','/observer/launch_gate.py'],env=ENV,check=True)
            for filename in ('completion_runner_v4.py','claude_subscription_runner.py'):
                data=(ROOT/filename).read_bytes()
                if filename=='completion_runner_v4.py':assert hashlib.sha256(data).hexdigest()==manifest['runnerSha256']
                script='import pathlib,sys;p=pathlib.Path("/observer/'+filename+'");p.write_bytes(sys.stdin.buffer.read());p.chmod(0o600)'
                subprocess.run([*shell(vm),'sudo','python3','-c',script],input=data,env=ENV,check=True)
        state['stage']='collecting';persist()
        def worker(index,vm):
            while True:
                with mutex:
                    provider=next((p for p in order if queues[p] and p not in owners and p not in state['blockedProviders']),None)
                    if provider is None:
                        if not owners:return
                    else:
                        owners.add(provider);order.remove(provider);order.append(provider)
                        state['workers'][vm]={'provider':provider,'stage':'authenticating'};persist()
                if provider is None:time.sleep(1);continue
                proc=None
                try:
                    with credential_lock: credential=previous.auth(provider)
                    available=credential.get('expiresAt',time.time()+7200)-time.time()-360
                    size=min(20,len(queues[provider]),int(available//320))
                    if size<1:raise ValueError('Subscription login needs renewal')
                    runid=f'completion-{provider}-v4-w{index+1}'
                    with mutex:
                        batch=[{**r,'workerVm':vm} for r in queues[provider][:size]]
                        state['runs'][runid]=vm
                        state['workers'][vm]={'provider':provider,'stage':'running','batchAttempts':len(batch)};persist()
                    proc=subprocess.Popen([*shell(vm),'sudo','python3','/observer/completion_runner_v4.py'],env=ENV,
                        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                    proc.stdin.write(json.dumps({**credential,'provider':provider,'runId':runid,'rows':batch}));proc.stdin.close()
                    finished=[];stop=None
                    for line in proc.stdout:
                        line=line.replace(credential['key'],'[REDACTED]')
                        print(vm+': '+line,end='',flush=True)
                        try:event=json.loads(line)
                        except ValueError:continue
                        if 'attempt' in event:
                            if event['attempt'] not in {r['episodeId'] for r in batch} or event['attempt'] in finished:raise ValueError('Unexpected attempt event')
                            finished.append(event['attempt'])
                            with mutex:
                                state['attempts'].append({**event,'provider':provider,'workerVm':vm})
                                state['completedAttempts']+=1;persist()
                        if 'batchStop' in event:stop=event['batchStop']
                    code=proc.wait()
                    with mutex:queues[provider][:]=[r for r in queues[provider] if r['episodeId'] not in finished]
                    if code or (stop and stop!='credential-expiry') or not finished:raise RuntimeError(stop or 'Batch execution failed')
                except Exception as error:
                    # Do not start another batch while a child might still be running.
                    if proc is not None:proc.wait()
                    with mutex:state['blockedProviders'][provider]={'errorType':type(error).__name__,'reason':str(error)[:200],'remaining':len(queues[provider])}
                finally:
                    with mutex:
                        owners.remove(provider);state['workers'][vm]={'stage':'idle'};persist()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(worker,i,vm) for i,vm in enumerate(VMS)]
                for future in futures:future.result()
        finally:
            state['stage']='archiving';persist()
            for runid,vm in state['runs'].items():
                result=subprocess.run([sys.executable,str(ROOT/'collect_parallel.py'),runid,'--vm',vm],env=ENV,capture_output=True,text=True)
                state['archiveExitCodes'][runid]=result.returncode;persist()
            for vm in VMS:
                result=subprocess.run([CLI,'stop',vm],env=ENV)
                state['vmStopExitCodes'][vm]=result.returncode;persist()
            finalize(state,manifest);persist()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    manifest=prepare()
    if args.execute:execute(manifest)
    else:print(json.dumps({k:v for k,v in manifest.items() if k!='rows'},indent=2))
