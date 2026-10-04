"""Manage only this benchmark's disposable VM; never mounts host directories."""
import argparse
import json
import os
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['start','stop','status','probe'])
args=parser.parse_args()
# Short path avoids macOS Unix-socket path limits. Isolated from normal ~/.lima.
state=Path.home()/'.cache'/'shell-bench-lima'
env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')}
env['LIMA_HOME']=str(state)
cli=str(root/'.runtime/bin/limactl')
name='shell-bench-d13'
if args.action=='start':
    state.mkdir(parents=True,exist_ok=True,mode=0o700)
    command = [cli,'start','--tty=false',name] if (state/name/'lima.yaml').exists() else [cli,'start','--tty=false','--name='+name,str(root/'vm.yaml')]
    subprocess.run(command,env=env,check=True)
elif args.action=='stop':
    subprocess.run([cli,'stop',name],env=env,check=True)
elif args.action=='status':
    subprocess.run([cli,'list',name,'--json'],env=env,check=True)
else:
    command=['sudo','-u','benchagent','sh','-c',
        'set -eu; id; test ! -r /home/benchadmin/.ssh/authorized_keys; echo controller-home-hidden; '
        'test ! -r /credentials; echo credentials-hidden; '
        'if sudo -n true 2>/dev/null; then echo unexpected-sudo-access; exit 1; fi; '
        'if findmnt -rn -t 9p,virtiofs; then echo unexpected-host-mount; exit 1; fi; '
        'grep CapEff /proc/self/status; '
        'bwrap --unshare-user --unshare-pid --ro-bind / / --proc /proc /bin/true']
    p=subprocess.run([cli,'shell',name,'--',*command],env=env,text=True,capture_output=True)
    record={'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,
            'nativeProviderPilotsPassed':False,'credentialIsolationValidated':False,
            'note':'Only an unprivileged nested-bubblewrap infrastructure probe; not provider readiness.'}
    (root/'vm-probe.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))
    raise SystemExit(p.returncode)
