"""Read-only VM/runtime provenance. No credentials or provider calls."""
import json
from pathlib import Path
import subprocess
from run_v3_pilot import CLI, VM, ENV, shell, ROOT

def main():
    fingerprint = shell('sudo','python3','/observer/rerun-v3/runtime_fingerprint.py',capture_output=True,text=True,check=True).stdout
    info = subprocess.check_output([CLI,'list',VM,'--json'],env=ENV,text=True)
    code = "import json,pathlib; r=pathlib.Path('/opt/bench'); names={'@anthropic-ai/claude-agent-sdk','@cursor/sdk','@qwen-code/sdk','@openai/codex'}; rows=[]\nfor p in r.rglob('package.json'):\n try:\n  v=json.loads(p.read_text())\n  if v.get('name') in names: rows.append({'name':v['name'],'version':v['version'],'path':str(p)})\n except (OSError,ValueError): pass\nprint(json.dumps(rows))"
    packages = shell('sudo','python3','-c',code,capture_output=True,text=True,check=True).stdout
    config = Path(ENV['LIMA_HOME'])/VM/'lima.yaml'
    report = {'fingerprint':json.loads(fingerprint),'vm':json.loads(info),
              'installedProviderPackages':json.loads(packages),
              'actualVmConfiguration':config.read_text(), 'providerCalls':0}
    (ROOT/'rerun-v3-environment.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'fingerprint':report['fingerprint'],'packages':report['installedProviderPackages']},indent=2))

if __name__ == '__main__': main()
