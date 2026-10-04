"""Install credential-free study controller/agent sources in the VM."""
import json
import os
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parent
env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')}
env['LIMA_HOME']=str(Path.home()/'.cache/shell-bench-lima')
cli=str(root/'.runtime/bin/limactl')
files=['study_runner.py','isolated_grade.py','test_isolated_grade.py','effects.py','test_effects.py','checks.py','corpus.py','broker.py','test_broker.py','network_guard.py','cases.json','development-cases.json','schedule.jsonl','providers.json','manifest.json','readiness.json','launch_gate.py','linux-agent.mjs']
subprocess.run([cli,'copy',*[str(root/f) for f in files],'shell-bench-d13:/home/benchadmin/'],env=env,check=True)
command='install -m 644 /home/benchadmin/linux-agent.mjs /opt/bench/agent/linux-agent.mjs\n'+''.join('install -m 600 /home/benchadmin/'+f+' /observer/'+f+'\n' for f in files if f!='linux-agent.mjs')
subprocess.run([cli,'shell','shell-bench-d13','--','sudo','sh','-c',command],env=env,check=True)
p=subprocess.run([cli,'shell','shell-bench-d13','--','sudo','python3','/observer/network_guard.py'],env=env,capture_output=True,text=True,check=True)
(root/'network-policy.json').write_text(p.stdout)
print('Study files and agent egress policy installed; no credentials copied.')
