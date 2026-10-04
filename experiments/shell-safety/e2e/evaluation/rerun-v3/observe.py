"""Linux inotify observer. Runs as the controller, outside the agent UID."""
import ctypes
import os
from pathlib import Path
import select
import struct
import threading

FLAGS = {1: 'ACCESS', 2: 'MODIFY', 4: 'ATTRIB', 8: 'CLOSE_WRITE', 16: 'CLOSE_NOWRITE',
         32: 'OPEN', 64: 'MOVED_FROM', 128: 'MOVED_TO', 256: 'CREATE', 512: 'DELETE',
         1024: 'DELETE_SELF', 2048: 'MOVE_SELF', 8192: 'UNMOUNT', 16384: 'OVERFLOW', 32768: 'IGNORED'}


class Observer:
    def __init__(self, root, watch_files=False):
        self.root = Path(root)
        self.lib = ctypes.CDLL(None, use_errno=True)
        self.fd = self.lib.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), 'inotify_init1')
        self.paths = {}
        self.events = []
        self.gaps = []
        self.stopping = threading.Event()
        self.add(self.root)
        for path in sorted(self.root.rglob('*')):
            if (path.is_dir() or (watch_files and path.is_file())) and not path.is_symlink():
                self.add(path)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def add(self, path):
        wd = self.lib.inotify_add_watch(self.fd, os.fsencode(path), 0xFFF)
        if wd < 0:
            self.gaps.append('watch failed: ' + str(path))
        else:
            self.paths[wd] = Path(path)

    def drain(self):
        while True:
            try:
                buf = os.read(self.fd, 1024 * 1024)
            except BlockingIOError:
                break
            pos = 0
            while pos < len(buf):
                wd, mask, cookie, length = struct.unpack_from('iIII', buf, pos)
                pos += 16
                name = os.fsdecode(buf[pos:pos + length].split(b'\0', 1)[0])
                pos += length
                path = self.paths.get(wd, self.root) / name
                flags = [value for bit, value in FLAGS.items() if mask & bit]
                if mask & (8192 | 16384):
                    self.gaps.append('inotify ' + ','.join(flags))
                if wd not in self.paths:
                    self.gaps.append('unmapped watch')
                self.events.append({'path': str(path.relative_to(self.root)), 'flags': flags, 'cookie': cookie,
                                    'isDirectory':bool(mask & 0x40000000)})
                if mask & 0x40000000 and mask & (128 | 256):
                    # Children can be touched before a new directory is watched.
                    # Preserve evidence but do not claim complete coverage.
                    self.gaps.append('new/moved directory watch race: ' + str(path.relative_to(self.root)))
                    if path.is_dir() and not path.is_symlink():
                        self.add(path)
                if mask & 32768:
                    self.paths.pop(wd, None)

    def run(self):
        while not self.stopping.is_set():
            if select.select([self.fd], [], [], 0.02)[0]:
                self.drain()

    def close(self):
        self.stopping.set()
        self.thread.join(timeout=2)
        self.drain()
        os.close(self.fd)


def snapshot(root):
    """Do not follow links or read data outside the disposable world."""
    import stat
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            info = path.lstat()
            item = {'mode': stat.S_IMODE(info.st_mode)}
            if path.is_symlink():
                item.update(kind='link', target=os.readlink(path))
            elif path.is_dir():
                item.update(kind='directory')
            elif path.is_file():
                data = path.read_bytes()
                import hashlib
                item.update(kind='file', sha256=hashlib.sha256(data).hexdigest(),
                            content=data.decode('utf8', errors='replace'))
            else:
                item.update(kind='special')
            result[str(path.relative_to(root))] = item
    return result
