"""Root-only exec shim; avoids preexec_fn in a multi-threaded controller."""
import os
from pathlib import Path
import sys

assert os.geteuid()==0
group=Path(sys.argv[1])
assert group.parent==Path('/sys/fs/cgroup') and group.name.startswith('bench-')
(group/'cgroup.procs').write_text(str(os.getpid()))
os.execvpe(sys.argv[2],sys.argv[2:],os.environ)
