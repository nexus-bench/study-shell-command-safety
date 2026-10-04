import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import parallel_study as job

class DispatcherTests(unittest.TestCase):
    def simulate(self,fail=False):
        seen=[];active=set();guard=threading.Lock();peak=[0];failed=[False]
        class Input(io.StringIO):
            def close(self):pass
        class Process:
            def __init__(self,*args,**kwargs):self.stdin=Input();self.stdout=self.lines()
            def lines(self):
                payload=json.loads(self.stdin.getvalue());provider=payload['provider']
                with guard:
                    assert provider not in active
                    active.add(provider);peak[0]=max(peak[0],len(active))
                try:
                    time.sleep(.02)
                    for row in payload['rows']:
                        with guard:
                            assert row['episodeId'] not in seen
                            seen.append(row['episodeId'])
                        yield json.dumps({'attempt':row['episodeId'],'terminalStatus':'completed'})+'\n'
                        if fail and provider=='claude' and not failed[0]:
                            failed[0]=True
                            yield json.dumps({'batchStop':'investigate-failed-attempt'})+'\n'
                            break
                finally:
                    with guard:active.remove(provider)
            def wait(self):return 0
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)
            for name in ('completion_runner_v3.py','claude_subscription_runner.py'):(dest/name).write_text('fixture')
            rows=[{'episodeId':f'{provider}-{i}','provider':provider} for provider in ('claude','codex','cursor','qwen') for i in range(43)]
            manifest={'expectedAttempts':len(rows),'preservedPrimaryEpisodes':0,'rows':rows,
                'runnerSha256':job.hashlib.sha256(b'fixture').hexdigest()}
            with patch.object(job,'ROOT',dest),patch.object(job,'JOB',dest),patch.object(job.previous,'auth',return_value={'key':'secret-fixture'}),patch.object(job.subprocess,'Popen',Process),patch.object(job.subprocess,'run',return_value=type('Result',(),{'returncode':0})()),patch.object(job,'finalize'),patch('builtins.print'):
                job.execute(manifest)
            state=json.loads((dest/'job-status.json').read_text())
        self.assertEqual(peak[0],2)
        self.assertEqual(len(seen),len(set(seen)))
        self.assertEqual(state['completedAttempts'],len(seen))
        self.assertEqual(len(state['vmStopExitCodes']),2)
        if fail:
            self.assertEqual(sum(x.startswith('claude-') for x in seen),1)
            self.assertIn('claude',state['blockedProviders'])
            self.assertEqual(len(seen),130)
        else:
            self.assertEqual(len(seen),172)
            self.assertFalse(state['blockedProviders'])
    def test_disjoint_parallel_dispatch(self):self.simulate()
    def test_failed_provider_not_retried(self):self.simulate(fail=True)

if __name__=='__main__':unittest.main()
