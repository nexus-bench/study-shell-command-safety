"""Deploy credential-free source files; never copies .env into the guest."""
import os
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parent
env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')}
env['LIMA_HOME']=str(Path.home()/'.cache/shell-bench-lima')
cli=str(root/'.runtime/bin/limactl')
files=[root/'linux-agent.mjs',root/'linux-pilot.py',root/'broker.py',root/'lock_process.c',
       root/'canary-probe.mjs',root/'enter-cgroup.py',root/'observer-probe.py',
       root.parent/'cases.json',root.parent/'development/observe.py',root.parents[2]/'rpc.mjs']
subprocess.run([cli,'copy',*[str(p) for p in files],'shell-bench-d13:/home/benchadmin/'],env=env,check=True)
command='''set -eu
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends gcc libc6-dev
install -d -m 755 /opt/bench/agent
install -m 644 /home/benchadmin/linux-agent.mjs /home/benchadmin/rpc.mjs /home/benchadmin/canary-probe.mjs /opt/bench/agent/
gcc -shared -fPIC -I/opt/bench/node-v24.14.0-linux-arm64/include/node /home/benchadmin/lock_process.c -o /opt/bench/agent/lock_process.node
install -m 600 /home/benchadmin/linux-pilot.py /home/benchadmin/observe.py /home/benchadmin/broker.py /home/benchadmin/enter-cgroup.py /observer/
install -m 600 /home/benchadmin/observer-probe.py /observer/
install -m 600 /home/benchadmin/cases.json /observer/pilot-cases.json
'''
subprocess.run([cli,'shell','shell-bench-d13','--','sudo','sh','-c',command],env=env,check=True)
