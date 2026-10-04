"""Credential-free second-worker validation; always stop it afterward."""
import json
from pathlib import Path
import subprocess
from run_v3_pilot import CLI, ENV, ROOT

VM='shell-bench-d13-worker2'
def shell(*args,**kw): return subprocess.run([CLI,'shell',VM,'--',*args],env=ENV,**kw)

def main():
    report={'providerEpisodesRun':0,'fullEvaluationStarted':False}
    try:
        subprocess.run([CLI,'start','--tty=false',VM],env=ENV,check=True)
        state=json.loads(subprocess.check_output([CLI,'list',VM,'--json'],env=ENV,text=True))
        primary=json.loads((ROOT/'rerun-v3-environment.json').read_text())
        assert state['cpus']==primary['vm']['cpus'] and state['memory']==primary['vm']['memory']
        assert state['config']['images']==primary['vm']['config']['images']
        mounts=shell('findmnt','-rn','-t','9p,virtiofs',capture_output=True,text=True)
        assert mounts.returncode in (0,1) and not mounts.stdout.strip()
        shell('sudo','mkdir','-p','/observer/rerun-v3',check=True)
        subprocess.run([CLI,'copy',str(ROOT/'rerun-v3'),VM+':/home/benchadmin/'],env=ENV,check=True)
        shell('sudo','cp','-R','/home/benchadmin/rerun-v3/.','/observer/rerun-v3/',check=True)
        shell('sudo','chmod','700','/observer/rerun-v3',check=True)
        fingerprint=json.loads(shell('sudo','python3','/observer/rerun-v3/runtime_fingerprint.py',capture_output=True,text=True,check=True).stdout)
        report['fingerprint']=fingerprint
        report['matchesPrimary']=fingerprint==primary['fingerprint']
        assert report['matchesPrimary'], 'Worker runtime drift'
        tests=shell('sudo','python3','/observer/rerun-v3/test_v2_vm.py','-v',capture_output=True,text=True)
        report.update(returncode=tests.returncode,stdout=tests.stdout,stderr=tests.stderr)
    except Exception as exc:
        report['error']=type(exc).__name__+': '+str(exc)
    finally:
        stop=subprocess.run([CLI,'stop',VM],env=ENV,capture_output=True,text=True)
        report.update(shutdownReturncode=stop.returncode,shutdownOutput=stop.stdout+stop.stderr)
        (ROOT/'rerun-v3-worker2-prechecks.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if report.get('error') or report.get('returncode')!=0 or report['shutdownReturncode']!=0: raise SystemExit(1)

if __name__=='__main__':main()
