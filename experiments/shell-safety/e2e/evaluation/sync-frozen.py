"""Deploy exactly the locally verified frozen files and evidence to the VM."""
import os
from pathlib import Path
import subprocess
from freeze import verify

root=Path(__file__).resolve().parent;frozen=verify()
env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')};env['LIMA_HOME']=str(Path.home()/'.cache/shell-bench-lima')
cli=str(root/'.runtime/bin/limactl')
entries=frozen['files']+[{'source':n,'deployed':n} for n in ('freeze.json','readiness.json','gate-evidence.json')]
subprocess.run([cli,'copy',*[str(root/e['source']) for e in entries],'shell-bench-d13:/home/benchadmin/'],env=env,check=True)
command=''.join('install -m 600 /home/benchadmin/'+e['deployed']+' /observer/'+e['deployed']+'\n' for e in entries)
subprocess.run([cli,'shell','shell-bench-d13','--','sudo','sh','-c',command],env=env,check=True)
subprocess.run([cli,'shell','shell-bench-d13','--','sudo','python3','/observer/launch_gate.py'],env=env,check=True)
