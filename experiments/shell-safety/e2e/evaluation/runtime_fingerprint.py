"""Fingerprint installed runtime bytes and OS package versions, excluding keys."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

def fingerprint():
    root=Path('/opt/bench');h=hashlib.sha256();count=0
    for base,dirs,files in os.walk(root,followlinks=False):
        dirs.sort()
        for name in sorted(files):
            p=Path(base)/name;h.update(str(p.relative_to(root)).encode()+b'\0')
            h.update(os.readlink(p).encode() if p.is_symlink() else hashlib.sha256(p.read_bytes()).digest());count+=1
    packages=subprocess.check_output(['dpkg-query','-W','-f=${Package}=${Version}\n'],text=True)
    return {'runtimeTreeSha256':h.hexdigest(),'runtimeFiles':count,'kernel':platform.release(),
            'architecture':platform.machine(),'packageInventorySha256':hashlib.sha256(packages.encode()).hexdigest()}

if __name__=='__main__':print(json.dumps(fingerprint(),indent=2))
