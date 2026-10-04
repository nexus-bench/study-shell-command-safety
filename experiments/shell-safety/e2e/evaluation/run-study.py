"""Host entry point. Default is preflight; full run requires --execute explicitly."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

root=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--development',action='store_true');p.add_argument('--run-id');p.add_argument('--limit',type=int,default=1440);args=p.parse_args()
if not args.execute and not args.development:
    raise SystemExit(subprocess.run(['python3',str(root/'launch_gate.py')]).returncode)
if args.execute and args.development:raise SystemExit('Choose development or full execution, not both')
if args.execute:subprocess.run(['python3',str(root/'launch_gate.py')],check=True)
data={}
for line in Path(__import__("os").environ["BENCH_CREDENTIALS_FILE"]).read_text().splitlines():
    if '=' not in line or line.lstrip().startswith('#'):continue
    k,v=line.split('=',1);parts=shlex.split(v,comments=True);data[k.strip().removeprefix('export ')]=parts[0] if parts else ''
keys={k:data[k] for k in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','CURSOR_API_KEY','OPENROUTER_API_KEY')}
if not all(keys.values()):raise SystemExit('Missing provider credential')
env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')};env['LIMA_HOME']=str(Path.home()/'.cache/shell-bench-lima')
runid=args.run_id or ('development-' if args.development else 'study-')+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
cmd=[str(root/'.runtime/bin/limactl'),'shell','shell-bench-d13','--','sudo','python3','/observer/study_runner.py','--run-id',runid,'--limit',str(args.limit)]
if args.development:cmd.append('--development')
proc=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
proc.stdin.write(json.dumps({'keys':keys}));proc.stdin.close()
for line in proc.stdout:
    for key in keys.values():line=line.replace(key,'[REDACTED]')
    print(line,end='',flush=True)
raise SystemExit(proc.wait())
