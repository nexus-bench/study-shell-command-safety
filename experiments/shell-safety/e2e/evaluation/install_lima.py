"""Install a checksum-pinned local Lima binary, without changing system PATH."""
import hashlib
from pathlib import Path
import platform
import subprocess
import tarfile
import urllib.request

assert platform.system() == 'Darwin' and platform.machine() == 'arm64'
root = Path(__file__).resolve().parent / '.runtime'
root.mkdir(exist_ok=True)
archive = root / 'lima-2.2.0-Darwin-arm64.tar.gz'
digest = 'bbdef91774885a0d05f7b048c4eb89ae2bcf3a0c252ae7ca7934e63df76d93c3'
if not archive.exists():
    urllib.request.urlretrieve('https://github.com/lima-vm/lima/releases/download/v2.2.0/' + archive.name, archive)
assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest, 'archive checksum mismatch'
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        p = Path(member.name)
        if p.is_absolute() or '..' in p.parts or member.islnk() or member.isdev():
            raise ValueError('unexpected archive path/link')
        if member.issym() and not (root/p.parent/member.linkname).resolve().is_relative_to(root.resolve()):
            raise ValueError('archive link escapes installation')
    tar.extractall(root)
subprocess.run([str(root/'bin/limactl'),'--version'],check=True)
subprocess.run([str(root/'bin/limactl'),'validate',str(root.parent/'vm.yaml')],check=True)
