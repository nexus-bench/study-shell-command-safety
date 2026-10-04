"""Collect redacted controller artifacts; retain reservations for interrupted runs."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument("--vm",choices=["shell-bench-d13","shell-bench-d13-worker2"],required=True);a=p.parse_args()
if not a.run_id.replace('-','').isalnum():raise SystemExit('Invalid run ID')
root=Path(__file__).resolve().parent;env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')}
env['LIMA_HOME']=str(Path.home()/'.cache/shell-bench-lima')
blob=subprocess.check_output([str(root/'.runtime/bin/limactl'),'shell',a.vm,'--','sudo','tar','-czf','-','-C','/observer/study-results',a.run_id],env=env)
dest=root/'study-results';dest.mkdir(exist_ok=True);(dest/(a.run_id+'.tar.gz')).write_bytes(blob)
with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
    for member in archive.getmembers():
        path=Path(member.name)
        if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):raise ValueError('Unsafe archive member')
    record_names=[m.name for m in archive.getmembers() if m.isfile() and m.name.endswith('.json') and Path(m.name).name!='verification.json']
    archive.extractall(dest,filter='data')
directory=dest/a.run_id
records=[json.loads((dest/name).read_text()) for name in sorted(record_names)]
reservations=[json.loads(f.read_text()) for f in directory.glob('*.started')]
finished={r['episodeId'] for r in records}
for row in reservations:
    if row['episodeId'] not in finished:
        records.append({**row,'terminalStatus':'runtime-error','taskCompleted':None,'unauthorizedEffectsObserved':None,'runtimeError':'Interrupted after reservation; no automatic retry','elapsedMs':None})
(directory/'results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
summary={'runId':a.run_id,'recorded':len(records),'completed':sum(r.get('taskCompleted') is True for r in records),
         'semanticPending':sum(r.get('semanticReviewRequired',False) for r in records),
         'gradingErrors':[r['episodeId'] for r in records if r.get('gradingError')],
         'credentialLeakDetected':any(r.get('credentialLeakDetected',True) for r in records),
         'unauthorizedFinalChanges':sum(len(r.get('unauthorizedFinalChanges',[])) for r in records),
         'archiveSha256':hashlib.sha256(blob).hexdigest(),
         'terminalStatuses':{s:sum(r.get('terminalStatus')==s for r in records) for s in sorted({r.get('terminalStatus') for r in records})}}
(directory/'verification.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
