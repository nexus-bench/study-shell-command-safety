"""Copy already-redacted pilot records and traces out of the controller."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

parser=argparse.ArgumentParser();parser.add_argument('run_id');args=parser.parse_args()
assert len(args.run_id)==16 and args.run_id[8]=='T' and args.run_id[-1]=='Z'
assert args.run_id[:8].isdigit() and args.run_id[9:-1].isdigit()
root=Path(__file__).resolve().parent
env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')}
env['LIMA_HOME']=str(Path.home()/'.cache/shell-bench-lima')
command=[str(root/'.runtime/bin/limactl'),'shell','shell-bench-d13','--','sudo','tar','-czf','-',
         '-C','/observer/results',args.run_id]
data=subprocess.check_output(command,env=env)
dest=root/'linux-results';dest.mkdir(exist_ok=True)
(dest/(args.run_id+'.tar.gz')).write_bytes(data)
with tarfile.open(fileobj=io.BytesIO(data)) as archive:
    for member in archive.getmembers():
        path=Path(member.name)
        if path.is_absolute() or '..' in path.parts or member.issym() or member.islnk() or member.isdev():
            raise ValueError('unexpected archive member')
    archive.extractall(dest,filter='data')
records=[json.loads(p.read_text()) for p in (dest/args.run_id).glob('*.json') if p.name not in ('summary.json','verification.json')]
summary={'runId':args.run_id,'environment':'Debian 13 ARM64 VM','records':len(records),
         'completed':sum(r['taskCompleted'] for r in records),
         'protectedFinalChanges':sum(len(r['protectedFinalChanges']) for r in records),
         'credentialLeakDetected':any(r.get('credentialLeakDetected',True) for r in records),
         'archiveSha256':hashlib.sha256(data).hexdigest(),
         'providers':{p:{'cases':sum(r['provider']==p for r in records),
                         'completed':sum(r['provider']==p and r['taskCompleted'] for r in records)}
                      for p in ('claude','codex','cursor','qwen')},
         'scope':'benign integration only; native Qwen auto policy plus outer VM containment; other three native sandboxes explicitly enabled'}
(dest/args.run_id/'verification.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
