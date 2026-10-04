"""Wait for the current batches to archive, then resume with the authorized retry."""
import fcntl
import json
import subprocess
import time
import parallel_study_v4 as job

def main():
    job.JOB.mkdir(exist_ok=True,parents=True)
    with (job.JOB/'handoff.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=job.JOB/'handoff-status.json'
        if path.exists():raise ValueError('Handoff already exists; inspect before restarting')
        state={'stage':'waiting-for-active-batches','authorizedRetry':job.REPLACE_EPISODE}
        job.save(path,state)
        try:
            deadline=time.monotonic()+7200
            while True:
                prior=json.loads((job.previous.JOB/'job-status.json').read_text())
                if prior['stage'] in ('needs-attention','collected-pending-review'):break
                if time.monotonic()>deadline:raise TimeoutError('Prior collection did not finish handoff within two hours')
                time.sleep(5)
            manifest=job.prepare()
            state.update(stage='starting-workers',expectedAttempts=manifest['expectedAttempts'],preservedPrimaryEpisodes=manifest['preservedPrimaryEpisodes'])
            job.save(path,state)
            for vm in job.VMS:
                subprocess.run([job.CLI,'start',vm,'--tty=false'],env=job.ENV,check=True)
            state['stage']='supervising-resumed-collection';job.save(path,state)
            job.execute(manifest)
            state['stage']='finished';job.save(path,state)
        except Exception as error:
            state.update(stage='needs-attention',errorType=type(error).__name__,reason=str(error)[:300])
            job.save(path,state)
            raise

if __name__=='__main__':main()
