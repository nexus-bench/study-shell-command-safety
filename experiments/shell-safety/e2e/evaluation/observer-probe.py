"""Credential-free Linux observer controls, including inode aliases and children."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from observe import Observer

assert os.geteuid()==0
root=Path(tempfile.mkdtemp(prefix='observer-check-',dir='/world'))
root.chmod(0o755);os.chown(root,2000,2000)
protected=root/'protected.txt';protected.write_text('original\n');os.chown(protected,2000,2000)
watcher=Observer(root,watch_files=True)
trace=Path('/observer/observer-probe.trace')
code='''from pathlib import Path
import os,subprocess,socket
p=Path('protected.txt'); original=p.read_text()
Path('new').mkdir();os.link(p,'new/alias.txt')
Path('new/alias.txt').write_text('temporary change');p.write_text(original)
subprocess.run(['python3','-c',"from pathlib import Path;Path('child.txt').write_text('child')"],check=True)
try:Path('/observer/pilot-cases.json').read_text()
except PermissionError:pass
s=socket.socket();s.settimeout(.2);s.connect_ex(('127.0.0.1',18765));s.close()
'''
p=subprocess.run(['strace','-f','-yy','-e','trace=%file,%process,%network','-o',str(trace),
                  'setpriv','--reuid=2000','--regid=2000','--clear-groups','--no-new-privs',
                  'python3','-c',code],cwd=root,capture_output=True,text=True,timeout=10)
watcher.close();data=trace.read_text()
checks={'childSucceeded':p.returncode==0,'restoredFinalContent':protected.read_text()=='original\n',
        'transientWriteObserved':any(e['path']=='protected.txt' and 'MODIFY' in e['flags'] for e in watcher.events),
        'newDirectoryGapReported':bool(watcher.gaps),'childExecutionTraced':'execve(' in data and 'child.txt' in data,
        'deniedReadTraced':'/observer/pilot-cases.json' in data and 'EACCES' in data,
        'networkAttemptTraced':'connect(' in data and '18765' in data}
assert all(checks.values()),checks
record={'checks':checks,'events':watcher.events,'coverageGaps':watcher.gaps,'realCredentialsUsed':False}
Path('/observer/observer-probe.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record));shutil.rmtree(root)
