"""Verify provider selection, no retries, and fail-closed subscription orchestration."""
import contextlib
import importlib.util
import io
import http.client
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent

class SubscriptionRunnerTests(unittest.TestCase):
    def run_wrapper(self, directory, failed=False):
        root = Path(directory)
        (root/'network-policy.json').write_text('{"rules":"test"}')
        (root/'cases.json').write_text('[{"id":"case"}]')
        rows = [{'episodeId':f'{provider}-{i}', 'caseId':'case','provider':provider}
                for i in range(360) for provider in ('codex','claude','cursor','qwen')]
        (root/'schedule.jsonl').write_text('\n'.join(map(json.dumps,rows)))
        calls=[]
        def episode(case,row,keys,output):
            calls.append(row)
            self.assertEqual(keys, {'OPENAI_API_KEY':'test-token'})
            return {**row,'terminalStatus':'runtime-error' if failed else 'completed',
                    'taskCompleted':True,'gradingError':None,'credentialLeakDetected':False}
        original = types.SimpleNamespace(ROOT=root, run_episode=episode,
                                         outer_command=lambda world: [], save=lambda path,record: None)
        spec=importlib.util.spec_from_file_location('subscription_under_test',ROOT/'subscription_runner.py')
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'study_runner':original}):
            spec.loader.exec_module(module)
        real_path=Path
        def mapped(value):
            if value=='/observer/study-results':return root/'results'
            if value=='/sys/fs/cgroup':return root/'groups'
            return real_path(value)
        real_open=open
        def opened(value,*args,**kwargs):
            return real_open(root/'lock' if value=='/observer/study.lock' else value,*args,**kwargs)
        with contextlib.ExitStack() as stack:
            agent=root/'test-agent.mjs';agent.write_text('test')
            stack.enter_context(patch.object(module,'prepare_agent',return_value=agent))
            stack.enter_context(patch.object(module,'Path',mapped))
            stack.enter_context(patch.object(module.os,'geteuid',return_value=0))
            stack.enter_context(patch.object(module.ctypes,'CDLL'))
            stack.enter_context(patch.object(module.subprocess,'run'))
            stack.enter_context(patch.object(module.broker,'http',types.SimpleNamespace(client=http.client)))
            stack.enter_context(patch('builtins.open',opened))
            stack.enter_context(patch.object(sys,'argv',['runner','--run-id','test']))
            stack.enter_context(patch.object(sys,'stdin',io.StringIO('{"accessToken":"test-token","accountId":"test-account"}')))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            if failed:
                with self.assertRaises(SystemExit):module.main()
            else:module.main()
            connection = module.broker.http.client.HTTPSConnection('example.invalid',timeout=1)
            self.assertIsNot(type(connection), http.client.HTTPSConnection)
            connection.close()
        return calls

    def test_only_codex_and_no_automatic_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            calls=self.run_wrapper(directory)
            self.assertEqual(len(calls),360)
            self.assertTrue(all(r['provider']=='codex' and r['authenticationMode']=='chatgpt-subscription' for r in calls))
            self.assertEqual(self.run_wrapper(directory),[])

    def test_service_failure_stops_after_first_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(len(self.run_wrapper(directory,failed=True)),1)

if __name__=='__main__':unittest.main()
