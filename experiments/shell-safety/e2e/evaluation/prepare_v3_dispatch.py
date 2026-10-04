"""Prepare deterministic worker assignments only; never starts a worker."""
import json
from pathlib import Path
import hashlib

ROOT=Path(__file__).resolve().parent

def main():
    rows=[json.loads(x) for x in (ROOT/'rerun-v3/evaluation-schedule.jsonl').read_text().splitlines()]
    env=json.loads((ROOT/'rerun-v3-environment.json').read_text())
    workers={'worker-a':['claude','codex'],'worker-b':['cursor','qwen']}
    assigned=[]; shards={}
    for name,providers in workers.items():
        subset=[r for r in rows if r['provider'] in providers]
        target=ROOT/('rerun-v3-'+name+'.jsonl')
        target.write_text(''.join(json.dumps(r)+'\n' for r in subset))
        assigned.extend(r['episodeId'] for r in subset)
        shards[name]={'providers':providers,'episodes':len(subset),'schedule':target.name,
                      'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    assert len(assigned)==len(set(assigned))==1584
    assert set(assigned)=={r['episodeId'] for r in rows}
    plan={'status':'prepared-not-authorized','launchAllowed':False,'episodes':1584,'cases':132,
          'repetitions':3,'providers':4,'workers':shards,
          'maxActiveEpisodesPerWorker':1,'maxActiveEpisodesPerProvider':1,
          'expectedRuntimeFingerprint':env['fingerprint'],
          'actualValidatedVm':{'cpus':4,'memoryBytes':4294967296,'architecture':'aarch64','hostMounts':[]},
          'perEpisode':{'cpu':2,'memoryBytes':3221225472,'pids':256,'wallSeconds':300},
          'retryPolicy':'No automatic retries. Preserve every reservation/result; manual infrastructure classification and separate explicit authorization before an additional attempt.',
          'workerPreflight':'Both workers passed credential-free checks and matched image/runtime at preparation. Recheck saved configuration, runtime bytes, kernel and package inventory before any provider call.',
          'reservationPolicy':'Each episode reserved with exclusive creation before launch. Never silently skip or replace a started-without-result record; report it as incomplete and investigate.',
          'finishPolicy':'Archive and verify every expected episode ID, preserve raw attempts, stop both VMs, then perform blinded semantic/action review.',
          'launchProcedure':'Full evaluation is blocked by the disabled authorization record. After explicit authorization, bind that record to the freeze digest and worker names, then use full_study_runner.py; its gate verifies integrity and worker environment before credentials are read.'}
    (ROOT/'rerun-v3-dispatch-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps({'prepared':True,'episodes':len(assigned),'launchAllowed':False}))

if __name__=='__main__':main()
