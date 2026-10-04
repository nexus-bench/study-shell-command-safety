"""Run only four development cases per subscription provider, then stop the VM."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent

def credentials(provider):
    if provider == 'claude':
        result = subprocess.run(['security', 'find-generic-password', '-s',
            'Claude Code-credentials', '-w'], capture_output=True, text=True, check=True)
        auth = json.loads(result.stdout)['claudeAiOauth']
        if auth.get('subscriptionType') not in ('pro', 'max', 'team', 'enterprise'):
            raise ValueError('Subscription login required')
        payload = {'accessToken': auth['accessToken'], 'expiresAt': auth['expiresAt']}
        expiry = auth['expiresAt']/1000
    else:
        auth = json.loads((Path.home()/'.codex/auth.json').read_text())
        if auth.get('auth_mode') != 'chatgpt':
            raise ValueError('Subscription login required')
        auth = auth['tokens']
        payload = {'accessToken': auth['access_token'], 'accountId': auth['account_id']}
        segment = auth['access_token'].split('.')[1]
        expiry = json.loads(base64.urlsafe_b64decode(segment+'='*(-len(segment)%4)))['exp']
    if expiry < time.time()+600:
        raise ValueError('Subscription token expires soon; refresh native login')
    return payload

def main():
    stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    env = {k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','TMPDIR','LANG')}
    env['LIMA_HOME'] = str(Path.home()/'.cache/shell-bench-lima')
    shell = [str(ROOT/'.runtime/bin/limactl'), 'shell', 'shell-bench-d13', '--']
    summary = {'smokeOnly': True, 'providers': {}}
    destination = ROOT/'study-results'/('subscription-smoke-'+stamp+'.json')
    subprocess.run([sys.executable, str(ROOT/'vm.py'), 'start'], env=env, check=True)
    try:
        for provider, filename in (('claude','claude_subscription_runner.py'), ('codex','subscription_runner.py')):
            runid = provider+'-subscription-smoke-'+stamp
            output = ROOT/'study-results'/runid
            output.mkdir(parents=True, exist_ok=False)
            record = {'runId':runid}
            summary['providers'][provider] = record
            try:
                payload = credentials(provider)
                wrapper = (ROOT/filename).read_bytes()
                amendment = json.loads((ROOT/'study-results'/(provider+'-subscription-v1')/'amendment.json').read_text())
                if hashlib.sha256(wrapper).hexdigest() != amendment['runnerSha256']:
                    raise ValueError('Runner amendment hash mismatch')
                installer = 'import sys,pathlib; p=pathlib.Path("/observer/'+filename+'"); p.write_bytes(sys.stdin.buffer.read()); p.chmod(0o600)'
                subprocess.run([*shell,'sudo','python3','-c',installer], input=wrapper, env=env, check=True)
                print(provider+': starting four development cases', flush=True)
                result = subprocess.run([*shell,'sudo','python3','/observer/'+filename,
                    '--development','--run-id',runid], input=json.dumps(payload), env=env,
                    text=True, capture_output=True, timeout=1500)
                log = (result.stdout+'\n'+result.stderr).replace(payload['accessToken'],'[REDACTED]')
                (output/'smoke.log').write_text(log)
                record['runnerExitCode'] = result.returncode
                collected = subprocess.run([sys.executable,str(ROOT/'collect-study.py'),runid],env=env,capture_output=True,text=True)
                record['archiveExitCode'] = collected.returncode
                print(provider+': runner exit '+str(result.returncode)+', archive exit '+str(collected.returncode),flush=True)
            except Exception as error:
                record['errorType'] = type(error).__name__
                print(provider+': stopped ('+type(error).__name__+')',flush=True)
            destination.write_text(json.dumps(summary,indent=2)+'\n')
    finally:
        result = subprocess.run([sys.executable,str(ROOT/'vm.py'),'stop'],env=env)
        summary['vmStopExitCode'] = result.returncode
        destination.write_text(json.dumps(summary,indent=2)+'\n')
    print(str(destination),flush=True)

if __name__ == '__main__':
    main()
