"""Fail closed before any provider work; evidence must be checked by the operator."""
import hashlib
import json
from pathlib import Path
import sys
from freeze import verify

root=Path(__file__).resolve().parent
manifest=json.loads((root/'manifest.json').read_text())
corpus=json.loads((root/'cases.json').read_text())
assert hashlib.sha256(json.dumps(corpus,sort_keys=True).encode()).hexdigest()==manifest['corpusSha256']
assert hashlib.sha256((root/'schedule.jsonl').read_bytes()).hexdigest()==manifest['scheduleSha256']
evidence=json.loads((root/'readiness.json').read_text())
missing=[]
try:verify()
except (OSError,ValueError,KeyError) as error:missing.append('freeze:'+str(error))
for gate in manifest['launchGates']:
    record=evidence['gates'].get(gate,{})
    if record.get('status')!='passed' or not record.get('evidence'):
        missing.append(gate)
        continue
    p=(root/record['evidence']).resolve()
    if not p.is_relative_to(root) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=record.get('sha256'):
        missing.append(gate+':invalid-evidence')
print(json.dumps({'launchAllowed':not missing,'remainingGates':missing},indent=2))
sys.exit(bool(missing))
