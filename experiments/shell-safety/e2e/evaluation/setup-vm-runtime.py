"""Provision exact package lock inside the current benchmark VM, no secrets."""
import os
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parent
env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')}
env['LIMA_HOME']=str(Path.home()/'.cache/shell-bench-lima')
cli=str(root/'.runtime/bin/limactl')
subprocess.run([cli,'copy',str(root/'runtime-setup.py'),str(root.parent/'package.json'),
                str(root.parent/'package-lock.json'),'shell-bench-d13:/home/benchadmin/'],env=env,check=True)
subprocess.run([cli,'shell','shell-bench-d13','--','sudo','sh','-c',
                'install -d /opt/bench && cp /home/benchadmin/package.json /home/benchadmin/package-lock.json /opt/bench/ && python3 /home/benchadmin/runtime-setup.py'],env=env,check=True)
