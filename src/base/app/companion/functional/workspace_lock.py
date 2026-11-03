"""Serialize registry changes across local web/MCP processes; no data deletion."""
import os,time,threading
from functools import wraps
from contextlib import contextmanager

_locks={};_guard=threading.Lock();_depth=threading.local()

@contextmanager
def lock(folder):
    key=str(folder)
    with _guard:mutex=_locks.setdefault(key,threading.RLock())
    with mutex:
        depths=getattr(_depth,'values',{});_depth.values=depths
        if depths.get(key):
            depths[key]+=1
            try:yield
            finally:depths[key]-=1
            return
        with (folder/'.subject-registry.lock').open('a+b') as file:
            file.seek(0,2)
            if not file.tell():file.write(b'0');file.flush()
            file.seek(0);deadline=time.monotonic()+15
            while True:
                try:
                    if os.name=='nt':
                        import msvcrt
                        msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic()>deadline:raise ValueError('另一个本机进程正在整理学科工作区，请稍后重试') from None
                    time.sleep(.05)
            depths[key]=1
            try:yield
            finally:
                depths[key]=0;file.seek(0)
                if os.name=='nt':msvcrt.locking(file.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(file.fileno(),fcntl.LOCK_UN)

def serialized(method):
    @wraps(method)
    def call(self,*args,**kwargs):
        with lock(self.root.folder):return method(self,*args,**kwargs)
    return call
