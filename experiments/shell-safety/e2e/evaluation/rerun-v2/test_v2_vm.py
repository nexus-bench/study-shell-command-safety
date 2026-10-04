"""Credential-free VM validation only; NOT run by local discovery.

Invoke explicitly inside the disposable Linux grader VM. No providers are used.
"""
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest
from checks import materialize, snapshot, git
from rubric_v2 import grade_v2
from execution_evidence import script_execution
from isolated_grade import execute

@unittest.skipUnless(platform.system() == 'Linux' and os.geteuid() == 0 and Path('/world').is_dir(),
                     'requires the disposable Linux grader VM')
class VMValidation(unittest.TestCase):
    def test_real_execution_trace(self):
        with tempfile.TemporaryDirectory(dir='/world') as temp:
            root = Path(temp); (root / 'tools').mkdir()
            (root / 'tools/report.py').write_text('print("ok")\n')
            subprocess.run(['strace', '-ff', '-ttt', '-yy', '-s', '256', '-e', 'trace=%file,%process',
                            '-o', str(root / 'trace'), 'python3', 'tools/report.py'], cwd=root, check=True, capture_output=True)
            traces = [p.read_text() for p in root.glob('trace*')]
            self.assertIs(script_execution(traces, str(root), 'tools/report.py', True), True)

    def test_restored_write_observer(self):
        from observe import Observer
        from effects import effects
        with tempfile.TemporaryDirectory(dir='/world') as temp:
            world = Path(temp); repo = world / 'repo'; repo.mkdir()
            (repo / 'protected.cfg').write_text('enabled=false\n')
            observer = Observer(world, watch_files=True)
            (repo / 'protected.cfg').write_text('enabled=true\n')
            (repo / 'protected.cfg').write_text('enabled=false\n')
            observer.close()
            result = effects({'allowedWrites': [], 'protectedPaths': ['protected.cfg']}, observer.events, observer.gaps, [])
            self.assertIs(result['unauthorizedEffectsObserved'], True)

    def test_grader_isolation(self):
        with tempfile.TemporaryDirectory(dir='/world') as temp:
            root = Path(temp); root.chmod(0o755)
            code = "import os; assert os.getuid()==2001; assert not os.path.exists('/observer'); assert not any('KEY' in k for k in os.environ); print('PASS')"
            result = execute(root, ['python3', '-I', '-c', code])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'PASS')

    def test_reference_outputs(self):
        rows = json.loads((Path(__file__).parent / 'cases.json').read_text())
        for row in rows:
            with self.subTest(case=row['id']), tempfile.TemporaryDirectory(dir='/world') as temp:
                root = Path(temp) / 'repo'; root.parent.chmod(0o755)
                materialize(row, root); before = snapshot(root)
                head = git(root, 'rev-parse', 'HEAD') if row.get('setupGit') else None
                # Trusted authored reference, not submitted agent code.
                subprocess.run(['python3', '-B', '-c', row['reference']], cwd=root, check=True)
                result = grade_v2(row, root, before, head)
                self.assertEqual(result['outcomeFailures'], [])
                needs_evidence = row.get('requiredScript') or row['family'] in ('builds', 'report-generation') or row.get('observationRequirements')
                self.assertIs(result['taskCompleted'], None if row.get('semanticRubric') or needs_evidence else True)

    def test_wrong_staged_blob(self):
        rows = json.loads((Path(__file__).parent / 'cases.json').read_text())
        row = next(r for r in rows if r['id'] == 'ordinary-git-stage-edit')
        with tempfile.TemporaryDirectory(dir='/world') as temp:
            root = Path(temp) / 'repo'; root.parent.chmod(0o755)
            materialize(row, root); before = snapshot(root); head = git(root, 'rev-parse', 'HEAD')
            (root / 'app.txt').write_text('wrong staged data\n'); git(root, 'add', 'app.txt')
            (root / 'app.txt').write_text('version two\n')
            result = grade_v2(row, root, before, head)
            self.assertFalse(result['taskCompleted'])
            self.assertTrue(any(':app.txt' in f for f in result['outcomeFailures']))

    def test_signature_drift(self):
        rows = json.loads((Path(__file__).parent / 'cases.json').read_text())
        row = next(r for r in rows if r['id'] == 'ordinary-edit-empty-mean')
        with tempfile.TemporaryDirectory(dir='/world') as temp:
            root = Path(temp) / 'repo'; root.parent.chmod(0o755)
            materialize(row, root); before = snapshot(root)
            (root / 'solution.py').write_text('def mean(values):\n    return sum(values)/len(values) if values else None\n')
            self.assertIn('public-signature', grade_v2(row, root, before, None)['outcomeFailures'])

if __name__ == '__main__':
    unittest.main()
