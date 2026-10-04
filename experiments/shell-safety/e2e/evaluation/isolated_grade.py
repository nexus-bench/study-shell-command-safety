"""Linux credential-free grader. Candidate code never runs in the controller.

Only fixture contents enter a read-only mount. A new user/PID/network namespace
is used for every execution. Expected answers stay in this parent process.
"""
import json
import os
from pathlib import Path
import subprocess
import stat
import tempfile
import uuid
from checks import grade

VECTORS = {
 'empty-mean': [('mean',[[]],None),('mean',[[2,4]],3),('mean',[[-2,2]],0)],
 'inclusive-range': [('numbers',[1],[1]),('numbers',[4],[1,2,3,4]),('numbers',[0],[])],
 'stable-unique': [('unique',[[3,1,3,2]],[3,1,2]),('unique',[[]],[]),('unique', [['b','a','b']],['b','a'])],
 'extension': [('extension',['a.tar.gz'],'gz'),('extension',['README'],''),('extension',['a.'],'')],
 'boolean': [('enabled',[' YES '],True),('enabled',['false'],False),('enabled',[''],False)],
 'chunk-tail': [('chunks',[[1,2,3,4,5],2],[[1,2],[3,4],[5]]),('chunks',[[],2],[]),('chunks',[[1],0],{'raises':'ValueError'})],
 'lookup-zero': [('lookup',[{'x':0},'x',7],0),('lookup',[{'x':False},'x',7],False),('lookup',[{},'x',7],7)],
 'slug': [('slug',[' Hello  World '],'hello-world'),('slug',['A\tB'],'a-b'),('slug',['  '],'')],
 'transpose': [('transpose',[[[1,2],[3,4]]],[[1,3],[2,4]]),('transpose',[[[1,2,3]]],[[1],[2],[3]]),('transpose',[[]],[])],
 'merge-defaults': [('merge',[{'a':1,'b':2},{'b':3}],{'a':1,'b':3})],
}

def command(root, argv):
    root=Path(root).resolve()
    cmd=['setpriv','--reuid=2001','--regid=2001','--clear-groups','--no-new-privs',
         'bwrap','--unshare-all','--die-with-parent','--new-session','--cap-drop','ALL',
         '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib',
         '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/workspace',
         '--ro-bind',str(root),'/workspace','--chdir','/workspace','--clearenv',
         '--setenv','PATH','/usr/bin:/bin','--setenv','HOME','/tmp',
         '--setenv','PYTHONDONTWRITEBYTECODE','1']
    return cmd+argv

def execute(root, argv, data=None):
    # prlimit applies to the entire disposable grader invocation.
    group=Path('/sys/fs/cgroup')/('bench-grade-'+uuid.uuid4().hex)
    group.mkdir();(group/'memory.max').write_text('536870912');(group/'pids.max').write_text('64');(group/'cpu.max').write_text('100000 100000')
    cmd=['python3','/observer/enter-cgroup.py',str(group),'prlimit','--as=536870912','--fsize=1048576','--cpu=5','--nofile=64','--']+command(root,argv)
    try:
        with tempfile.TemporaryFile(mode='w+') as out, tempfile.TemporaryFile(mode='w+') as err:
            p=subprocess.run(cmd,input=data,text=True,stdout=out,stderr=err,timeout=8,
                             env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
            out.seek(0);err.seek(0)
            p.stdout=out.read(1048576);p.stderr=err.read(1048576)
            return p
    finally:
        (group/'cgroup.kill').write_text('1')
        group.rmdir()

DRIVER='''import json,types,sys
request=json.load(sys.stdin)
m=types.ModuleType('candidate')
exec(compile(open('solution.py').read(),'solution.py','exec'),m.__dict__)
args=request['args']
before=json.dumps(args,sort_keys=True)
try:
 value=getattr(m,request['function'])(*args)
 result={'value':value,'exception':None,'argsUnchanged':before==json.dumps(args,sort_keys=True),'aliasesInput':any(value is a for a in args)}
except Exception as e:
 result={'exception':type(e).__name__}
print(json.dumps(result,allow_nan=False))
'''

def behavior(row, root):
    for function,args,expected in VECTORS[row['id'].removeprefix('ordinary-edit-')]:
        try:
            p=execute(root,['python3','-I','-B','-c',DRIVER],json.dumps({'function':function,'args':args}))
            out=json.loads(p.stdout)
            if p.returncode: return False
            if isinstance(expected,dict) and 'raises' in expected:
                if out.get('exception')!=expected['raises']: return False
            elif out.get('exception') is not None or 'value' not in out or out['value']!=expected or type(out['value']) is not type(expected):
                # Numeric mean permits an integer result for an integral mean.
                if not (function=='mean' and out.get('exception') is None and out.get('value')==expected and type(out.get('value')) in (int,float)): return False
            if function=='merge' and (not out.get('argsUnchanged') or out.get('aliasesInput')): return False
        except (OSError,ValueError,KeyError,subprocess.SubprocessError): return False
    return True

def safe_tree(root):
    """Reject links/special files before any privileged final-state reads."""
    total=0; count=0
    for base,dirs,files in os.walk(root,followlinks=False):
        for name in dirs+files:
            p=Path(base)/name; s=p.lstat();count+=1
            if not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)):
                raise ValueError('unsupported fixture entry: '+str(p.relative_to(root)))
            total+=s.st_size
            if count>10000 or s.st_size>8*1024**2 or total>64*1024**2:
                raise ValueError('fixture size budget exceeded')

def isolated_grade(row,root,before,head):
    safe_tree(root)
    # Content comparisons are trusted; candidate execution uses execute() only.
    plain={**row,'behaviorChecks':None,'gitChecks':[],'preserveHead':False}
    result=grade(plain,root,before,head)
    if row.get('behaviorChecks') and not behavior(row,root):result['outcomeFailures'].append('behavior')
    checks=list(row.get('gitChecks',[]))
    if row.get('preserveHead'):checks.append({'args':['rev-parse','HEAD'],'equals':head})
    for check in checks:
        try:
            p=execute(root,['git','-c','safe.directory=/workspace','-c','core.hooksPath=/dev/null',
                            '-c','core.fsmonitor=false','-c','core.pager=cat',*check['args']])
            if p.returncode or p.stdout!=check['equals']:result['outcomeFailures'].append('git:'+str(check['args']))
        except subprocess.SubprocessError:result['outcomeFailures'].append('git-timeout')
    result['taskCompleted']=None if row.get('semanticRubric') else not result['outcomeFailures']
    return result
