"""Create an explicit prelaunch byte freeze. Never enables gates implicitly."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
FILES=['study_runner.py','isolated_grade.py','effects.py','checks.py','corpus.py','broker.py',
       'linux-agent.mjs','lock_process.c','enter-cgroup.py','runtime_fingerprint.py','network_guard.py',
       'launch_gate.py','freeze.py','sync-frozen.py','run-study.py','collect-study.py','analyze.py','review_packets.py',
       'cases.json','schedule.jsonl','providers.json','manifest.json','network-policy.json',
       'runtime-fingerprint.json','semantic-review-protocol.json','PROTOCOL-AMENDMENTS.md',
       'vm.yaml','result-contract.json','../development/observe.py']

def verify():
    frozen=json.loads((ROOT/'freeze.json').read_text())
    for entry in frozen['files']:
        local=ROOT/entry['source']
        if str(ROOT)=='/observer':local=ROOT/entry['deployed']
        if not local.is_file() or hashlib.sha256(local.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('Frozen artifact changed: '+entry['source'])
    if str(ROOT)=='/observer':
        from runtime_fingerprint import fingerprint
        if fingerprint()!=json.loads((ROOT/'runtime-fingerprint.json').read_text()):
            raise ValueError('Installed runtime differs from frozen fingerprint')
    return frozen

if __name__=='__main__':
    data={'version':1,'scope':'collection-ready with explicit unknowns; publication requires semantic/effect adjudication',
          'files':[{'source':name,'deployed':Path(name).name,'sha256':hashlib.sha256((ROOT/name).read_bytes()).hexdigest()} for name in FILES]}
    (ROOT/'freeze.json').write_text(json.dumps(data,indent=2)+'\n')
    print('Frozen',len(data['files']),'artifacts')
