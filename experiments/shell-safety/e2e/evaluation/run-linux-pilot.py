"""Host launcher. Sends selected keys through SSH stdin, never args or files."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--provider',choices=['claude','codex','cursor','qwen'],action='append')
parser.add_argument('--case',dest='case_ids',action='append')
args=parser.parse_args()
root=Path(__file__).resolve().parent
env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')}
env['LIMA_HOME']=str(Path.home()/'.cache/shell-bench-lima')
data={}
for line in Path(__import__("os").environ["BENCH_CREDENTIALS_FILE"]).read_text().splitlines():
    if not line.strip() or line.lstrip().startswith('#') or '=' not in line: continue
    k,v=line.split('=',1)
    parts=shlex.split(v,comments=True)
    data[k.strip().removeprefix('export ')]=parts[0] if parts else ''
keynames={'claude':'ANTHROPIC_API_KEY','codex':'OPENAI_API_KEY','qwen':'OPENROUTER_API_KEY','cursor':'CURSOR_API_KEY'}
providers=args.provider or list(keynames)
keys={keynames[p]:data[keynames[p]] for p in providers}
assert all(keys.values()), 'missing provider key'
cli=str(root/'.runtime/bin/limactl')
command=[cli,'shell','shell-bench-d13','--','sudo','python3','/observer/linux-pilot.py']
p=subprocess.Popen(command,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
p.stdin.write(json.dumps({'keys':keys,'providers':providers,'caseIds':args.case_ids}));p.stdin.close()
for line in p.stdout:
    for secret in keys.values():line=line.replace(secret,'[REDACTED]')
    print(line,end='',flush=True)
stderr=p.stderr.read()
for secret in keys.values():stderr=stderr.replace(secret,'[REDACTED]')
if stderr:print(stderr)
raise SystemExit(p.wait())
