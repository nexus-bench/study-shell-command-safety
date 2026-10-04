"""Run as root INSIDE the disposable VM, never on the host."""
import hashlib
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import urllib.request

assert platform.system()=='Linux' and platform.machine()=='aarch64' and os.geteuid()==0
root=Path('/opt/bench')
root.mkdir(exist_ok=True)
name='node-v24.14.0-linux-arm64.tar.xz'
url='https://nodejs.org/dist/v24.14.0/'
sums=urllib.request.urlopen(url+'SHASUMS256.txt',timeout=30).read().decode()
digest=next(line.split()[0] for line in sums.splitlines() if line.split()[-1]==name)
archive=root/name
urllib.request.urlretrieve(url+name,archive)
assert hashlib.sha256(archive.read_bytes()).hexdigest()==digest
(root/'node-SHASUMS256.txt').write_text(sums)
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        if Path(member.name).is_absolute() or '..' in Path(member.name).parts or member.isdev():
            raise ValueError('invalid archive')
        if member.issym() and not (root/Path(member.name).parent/member.linkname).resolve().is_relative_to(root):
            raise ValueError('escaping link')
    tar.extractall(root)
node=root/'node-v24.14.0-linux-arm64/bin'
env={**os.environ,'PATH':str(node)+':/usr/bin:/bin'}
subprocess.run([str(node/'npm'),'ci','--ignore-scripts','--no-audit','--no-fund'],cwd=root,env=env,check=True)
subprocess.run([str(node/'node'),'--version'],check=True)
