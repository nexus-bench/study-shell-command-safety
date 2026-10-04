"""Prepare a separately gated evaluation entry point; authorization stays false."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent
BUNDLE=ROOT/'rerun-v3'

def main():
    source=(BUNDLE/'study_runner.py').read_text()
    source=source.replace("world=Path('/world')/eid;", "world=Path('/world')/('episode-'+hashlib.sha256(eid.encode()).hexdigest()[:24]);")
    source=source.replace('from action_evidence import action_review','from action_evidence import action_review\nfrom full_run_gate import check as full_gate')
    old="    approved=[json.loads(x) for x in (ROOT/'pilot-schedule.jsonl').read_text().splitlines()]\n    if control or schedule not in approved:\n        raise RuntimeError('Full evaluation blocked; development schedule only')"
    new="    worker='worker-a' if schedule['provider'] in ('claude','codex') else 'worker-b'\n    approved=full_gate(worker)\n    if control or schedule not in approved:\n        raise RuntimeError('Episode outside authorized frozen worker schedule')\n    frozen_rows={r['id']:r for r in json.loads((ROOT/'cases.json').read_text())}\n    if row!=frozen_rows.get(schedule['caseId']): raise RuntimeError('Case differs from frozen corpus')"
    assert old in source; source=source.replace(old,new)
    old="    args=parser.parse_args()\n    if not args.development or args.dry_run or args.limit!=76:\n        raise RuntimeError('Full evaluation blocked; development pilot only')"
    new="    parser.add_argument('--worker',required=True,choices=['worker-a','worker-b'])\n    args=parser.parse_args()\n    if args.development or args.dry_run or args.limit!=792:\n        raise RuntimeError('Full runner requires one complete 792-episode worker schedule')\n    full_gate(args.worker,live=True)"
    assert old in source; source=source.replace(old,new).replace('default=1584','default=792')
    source=source.replace("    if not args.dry_run and not args.development:subprocess.run([sys.executable,str(ROOT/'launch_gate.py')],check=True)",
        "    from network_guard import install\n    live_policy=install()\n    request=json.load(sys.stdin)")
    source=source.replace("    request={} if args.dry_run else json.load(sys.stdin)\n",'')
    # Live fixed-IP resolution rather than a potentially stale saved IP allowlist.
    old="    if not args.dry_run and not args.development:\n        policy=json.loads((ROOT/'network-policy.json').read_text())\n        subprocess.run(['nft','delete','table','inet','bench_agent'],capture_output=True)\n        subprocess.run(['nft','-f','-'],input=policy['rules'],text=True,check=True)"
    assert old in source; source=source.replace(old,'')
    source=source.replace("schedule=[json.loads(x) for x in (ROOT/'evaluation-schedule.jsonl').read_text().splitlines()]",'schedule=full_gate(args.worker)')
    source=source.replace("        if reservation.exists():continue", "        if reservation.exists():\n            if not (output/(s['episodeId']+'.json')).exists():\n                raise RuntimeError('Reserved episode has no result; investigate, do not retry automatically')\n            continue")
    source=source.replace("    keys=request.get('keys',{})", "    save(output/('network-policy-'+str(time.time_ns())+'.json'),live_policy)\n    keys=request.get('keys',{})")
    (BUNDLE/'full_study_runner.py').write_text(source)
    shutil.copyfile(ROOT/'full_run_gate_template.py',BUNDLE/'full_run_gate.py')
    fingerprint=json.loads((ROOT/'rerun-v3-environment.json').read_text())['fingerprint']
    (BUNDLE/'runtime-fingerprint.json').write_text(json.dumps(fingerprint,indent=2)+'\n')
    auth=ROOT/'rerun-v3-launch-authorization.json'
    if not auth.exists(): auth.write_text(json.dumps({'authorized':False,'freezeSha256':None,'workers':[]},indent=2)+'\n')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(BUNDLE.iterdir()) if p.is_file() and p.name!='candidate-hashes.json'}
    (BUNDLE/'candidate-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print('Prepared full-run entry point; authorization remains disabled.')

if __name__=='__main__':main()
