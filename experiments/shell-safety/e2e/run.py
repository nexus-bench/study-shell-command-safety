"""Bounded benign file-task pilot. Never pass arbitrary command corpora here."""
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

here=Path(__file__).resolve().parent
provider=sys.argv[1]
assert provider in ('qwen','cursor')
if provider=='qwen':
    key=os.environ.get('OPENROUTER_API_KEY','')
else:
    lines=Path(__import__("os").environ["BENCH_CREDENTIALS_FILE"]).read_text().splitlines()
    vals=[m.group(1) for line in lines if (m:=re.match(r'^\s*(?:export\s+)?CURSOR_API_KEY\s*=\s*(.*?)\s*$',line))]
    assert len(vals)==1
    key=vals[0].strip().strip('\"\'')
assert key, 'Required provider key missing'
cases=json.loads((here/'cases.json').read_text())
selected=cases if len(sys.argv)<3 else [c for c in cases if c['id']==sys.argv[2]]
assert selected
run_id=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
out=here/'results'/run_id/provider
out.mkdir(parents=True)
for case in selected:
    name='shell-study-'+uuid.uuid4().hex[:12]
    args=['docker','run','--rm','--name',name,'-i','--cap-drop=ALL','--security-opt=no-new-privileges',
          '--pids-limit=128','--memory=2g','--cpus=2','--read-only',
          '--tmpfs','/tmp:rw,exec,nosuid,size=512m',
          '--tmpfs','/home/node:rw,nosuid,size=128m,uid=1000,gid=1000','shell-safety-e2e:pilot']
    try:
        p=subprocess.run(args,input=json.dumps({'provider':provider,'key':key,'caseId':case['id']}),text=True,capture_output=True,timeout=150)
        raw=(p.stdout+'\n'+p.stderr).replace(key,'[REDACTED]')
        (out/(case['id']+'.log')).write_text(raw)
        scores=[json.loads(s) for s in raw.splitlines() if s.startswith('{') and json.loads(s).get('type')=='score']
        print(json.dumps(scores[-1] if scores else {'caseId':case['id'],'status':'infrastructure-error','exitCode':p.returncode}),flush=True)
    except subprocess.TimeoutExpired:
        subprocess.run(['docker','rm','-f',name],capture_output=True)
        (out/(case['id']+'.log')).write_text('Host timeout; container removed.\n')
        print(json.dumps({'caseId':case['id'],'status':'timeout'}),flush=True)
print('Records: '+str(out))
