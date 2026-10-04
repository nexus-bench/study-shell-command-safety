"""Predeclared 16-episode path-blinding validation, not a failure retry."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent
DEST=ROOT/'rerun-v3-opaque-smoke'

def main():
    shutil.copytree(ROOT/'rerun-v3',DEST,ignore=shutil.ignore_patterns('__pycache__'))
    ids={'v2-development-workflow-clean','v2-development-workflow-injected',
         'v3-pilot-boundary-migration-plan-authorized','v3-pilot-ordinary-build-inventory'}
    dev=[r for r in json.loads((DEST/'development-cases.json').read_text()) if r['id'] in ids]
    assert len(dev)==4
    schedule=[s for s in map(json.loads,(DEST/'pilot-schedule.jsonl').read_text().splitlines()) if s['caseId'] in ids]
    assert len(schedule)==16
    for s in schedule: s['episodeId']='opaque-'+s['episodeId']
    (DEST/'development-cases.json').write_text(json.dumps(dev,indent=2)+'\n')
    (DEST/'pilot-schedule.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in schedule))
    code=(DEST/'study_runner.py').read_text().replace('args.limit!=76','args.limit!=16')
    code=code.replace("world=Path('/world')/eid;", "world=Path('/world')/('episode-'+hashlib.sha256(eid.encode()).hexdigest()[:24]);")
    (DEST/'study_runner.py').write_text(code)
    # The smoke bundle contains no evaluation entry point.
    (DEST/'full_study_runner.py').unlink(); (DEST/'full_run_gate.py').unlink()
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DEST.iterdir() if p.is_file() and p.name!='candidate-hashes.json'}
    (DEST/'candidate-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    for old,new in [('precheck_v3_host.py','precheck_opaque_host.py'),('run_v3_pilot.py','run_opaque_pilot.py')]:
        code=(ROOT/old).read_text().replace('rerun-v3','rerun-v3-opaque-smoke').replace('v3-pilot','opaque-pilot').replace('76','16')
        (ROOT/new).write_text(code)
    print('Prepared 16 development episodes with opaque working directories; no calls started.')

if __name__=='__main__':main()
