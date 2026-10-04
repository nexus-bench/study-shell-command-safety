"""Freeze preparation artifacts and verify readiness without launching anything."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT/'rerun-v3'

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory():
    files = list(BUNDLE.glob('*')) + list((ROOT/'rerun-v3-opaque-smoke').glob('*')) + [ROOT/name for name in (
        'prepare_rerun.py','prepare_full_run.py','precheck_v3_host.py','run_v3_pilot.py',
        'capture_v3_environment.py','rerun-v3-vm-prechecks.json','rerun-v3-environment.json',
        'test_full_preparation.py','test_rerun_preparation.py','test_rubric_v2.py','test_effects.py',
        'freeze_v3.py','prepare_v3_dispatch.py','FULL-RUN-PREPARATION.md',
        'rerun-v3-dispatch-plan.json','rerun-v3-worker-a.jsonl','rerun-v3-worker-b.jsonl',
        'precheck_v3_worker2.py','rerun-v3-worker2-prechecks.json','review_v3_pilot.py',
        'review_packets_v3.py','summarize_v2_pilot.py','rerun-v3-local-prechecks.json',
        'prepare_v3_launcher.py','full_run_gate_template.py','prepare_opaque_smoke.py',
        'review_opaque_pilot.py','precheck_opaque_host.py','run_opaque_pilot.py',
        'rerun-v3-opaque-smoke-vm-prechecks.json')]
    return {str(p.relative_to(ROOT)):digest(p) for p in sorted(files) if p.is_file()}

def verify(record):
    errors = []
    for name, expected in record['sha256'].items():
        path = ROOT/name
        if not path.is_file() or digest(path)!=expected: errors.append('changed:'+name)
    required = ['rerun-v3-vm-prechecks.json', 'rerun-v3-local-prechecks.json',
                'rerun-v3-environment.json', 'rerun-v3-worker2-prechecks.json']
    for name in required:
        if not (ROOT/name).is_file(): errors.append('missing-local-evidence:'+name)
    if errors:
        return {'preparationChecksPassed':False, 'errors':errors, 'pending':[],
                'fullEvaluationStarted':False, 'launchAllowed':False}
    candidate = json.loads((BUNDLE/'candidate-hashes.json').read_text())
    for name, expected in candidate.items():
        if digest(BUNDLE/name)!=expected: errors.append('candidate-changed:'+name)
    if json.loads((ROOT/'rerun-v3-vm-prechecks.json').read_text())['returncode']!=0:
        errors.append('VM-prechecks-failed')
    if json.loads((ROOT/'rerun-v3-local-prechecks.json').read_text())['returncode']!=0:
        errors.append('local-prechecks-failed')
    expected={json.loads(x)['episodeId'] for x in (BUNDLE/'evaluation-schedule.jsonl').read_text().splitlines()}
    assigned=[]
    for worker in ('a','b'):
        assigned.extend(json.loads(x)['episodeId'] for x in (ROOT/f'rerun-v3-worker-{worker}.jsonl').read_text().splitlines())
    if len(assigned)!=1584 or len(set(assigned))!=1584 or set(assigned)!=expected:
        errors.append('worker-schedule-coverage')
    env = json.loads((ROOT/'rerun-v3-environment.json').read_text())
    worker2=json.loads((ROOT/'rerun-v3-worker2-prechecks.json').read_text())
    if worker2.get('returncode')!=0 or worker2.get('shutdownReturncode')!=0 or worker2.get('fingerprint')!=env['fingerprint']:
        errors.append('second-worker-validation')
    versions = {(p['name'],p['version']) for p in env['installedProviderPackages']}
    for name,version in [('@anthropic-ai/claude-agent-sdk','0.3.288'),('@cursor/sdk','1.0.35'),
                         ('@qwen-code/sdk','0.1.17'),('@openai/codex','0.160.0')]:
        if (name,version) not in versions: errors.append('runtime-version:'+name)
    pilot = record.get('pilot')
    pending = []
    smoke=record.get('smoke')
    if not smoke:
        pending.append('Opaque-path validation pilot')
    else:
        smoke_folder=ROOT/smoke
        status=json.loads((smoke_folder/'job-status.json').read_text())
        review=json.loads((smoke_folder/'pilot-review.json').read_text())
        if any(status.get(k)!=0 for k in ('returncode','archiveReturncode','shutdownReturncode')) or review.get('measurementReady') is not True:
            errors.append('opaque-pilot-validation')
        if json.loads((smoke_folder/'runtime-fingerprint.json').read_text())!=env['fingerprint']:
            errors.append('opaque-pilot-runtime-drift')
    if not pilot:
        pending.append('Revised 76-episode development pilot approval and completion')
    else:
        folder = ROOT/pilot
        status = json.loads((folder/'job-status.json').read_text())
        summary = json.loads((folder/'pilot-summary.json').read_text())
        if any(status.get(k)!=0 for k in ('returncode','archiveReturncode','shutdownReturncode')):
            errors.append('pilot-or-archive-or-shutdown-failed')
        if summary['completedRecords']!=76 or any(summary[k] for k in ('missing','extra','duplicates')):
            errors.append('pilot-record-coverage')
        for provider in ('claude','codex','cursor','qwen'):
            counts=summary['byProvider'].get(provider,{})
            if counts.get('episodes')!=19 or counts.get('terminal:completed')!=19:
                errors.append('pilot-terminal-coverage:'+provider)
            if any(counts.get(k) for k in ('gradingError','credentialLeakDetected','runtimeError')):
                errors.append('pilot-instrumentation:'+provider)
        if json.loads((folder/'runtime-fingerprint.json').read_text())!=env['fingerprint']:
            errors.append('pilot-environment-drift')
        for name,expected in json.loads((folder/'as-run-candidate-hashes.json').read_text()).items():
            if digest(BUNDLE/name)!=expected: errors.append('pilot-measured-artifact-drift:'+name)
        if not (folder/'pilot-review.json').is_file():
            pending.append('Pilot evidence review')
        elif json.loads((folder/'pilot-review.json').read_text()).get('measurementReady') is not True:
            pending.append('Resolve pilot measurement findings')
    return {'preparationChecksPassed':not errors,'errors':errors,'pending':pending,
            'fullEvaluationStarted':False,'launchAllowed':False,
            'launchAuthorization':'Not granted; disabled authorization record and full_run_gate block full evaluation.',
            'beforeLaunch':['Explicit full-study authorization',
                'Verify the frozen runtime fingerprint and OS configuration on every worker',
                'Install and verify the live network policy before credentials or episodes',
                'Authorize the exact freeze digest and frozen worker schedules; preserve reservations, no automatic retries'],
            'analysisRequirements':['Two independent blinded reviews and adjudication for semantic cases',
                'Trace-backed action review for all migration-plan/release-marker variants; unresolved labels stay null']}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--write',action='store_true')
    parser.add_argument('--pilot',type=Path)
    parser.add_argument('--smoke',type=Path)
    args=parser.parse_args()
    freeze=ROOT/'rerun-v3-freeze.json'
    if args.write:
        record={'version':3,'sha256':inventory(),'pilot':None,'smoke':None,'fullLaunchAuthorized':False}
        for kind, target in [('pilot',args.pilot),('smoke',args.smoke)]:
            if not target: continue
            folder=target.resolve()
            if not folder.is_relative_to(ROOT/'study-results'): raise ValueError('Pilot must be an archived local study result')
            record[kind]=str(folder.relative_to(ROOT))
            for p in folder.rglob('*'):
                if p.is_file(): record['sha256'][str(p.relative_to(ROOT))]=digest(p)
        freeze.write_text(json.dumps(record,indent=2)+'\n')
    record=json.loads(freeze.read_text())
    result=verify(record)
    (ROOT/'rerun-v3-readiness.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    raise SystemExit(bool(result['errors']))

if __name__=='__main__': main()
