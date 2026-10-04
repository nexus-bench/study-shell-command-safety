"""Supervise the frozen study, then collect artifacts and preliminary analysis.

Does not edit frozen files, retry episodes, or adjudicate semantic outcomes.
Run as a background host process; only the existing launcher reads credentials.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

root=Path(__file__).resolve().parent
runid='study-v1'
job=root/'study-results'/runid
job.mkdir(parents=True,exist_ok=True)
state=job/'job-status.json'

def status(stage,**extra):
    state.write_text(json.dumps({'runId':runid,'stage':stage,'updatedUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**extra},indent=2)+'\n')

def run(script,*args,output=None):
    if output:
        with output.open('w') as f:return subprocess.run([sys.executable,str(root/script),*args],stdout=f).returncode
    return subprocess.run([sys.executable,str(root/script),*args]).returncode

status('collecting')
code=run('run-study.py','--execute','--run-id',runid)
status('archiving',runnerExitCode=code)
collected=run('collect-study.py',runid)
if collected==0:
    analyzed=run('analyze.py',str(job/'results.jsonl'),output=job/'preliminary-analysis.json')
    reviewed=run('review_packets.py',str(job/'results.jsonl'),str(job/'semantic-review'))
else:analyzed=reviewed=None
stopped=run('vm.py','stop')
status('collection-finished' if code==collected==analyzed==reviewed==stopped==0 else 'needs-attention',
       runnerExitCode=code,archiveExitCode=collected,analysisExitCode=analyzed,
       reviewPacketExitCode=reviewed,vmStopExitCode=stopped,
       note='Preliminary only: semantic and unresolved trace outcomes require review before comparison claims.')
