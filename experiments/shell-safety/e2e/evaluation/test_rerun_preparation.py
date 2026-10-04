import ast
import hashlib
import json
from pathlib import Path
import unittest
from execution_evidence import script_execution
from prepare_rerun import amend, expansion, ROOT

class EvidenceTests(unittest.TestCase):
    def test_direct_execution(self):
        trace = '1.0 execve("/usr/bin/python3", ["python3", "tools/report.py"], 0x123 /* 3 vars */) = 0\n+++ exited with 0 +++'
        self.assertIs(script_execution([trace], '/repo', 'tools/report.py', True), True)
        self.assertIs(script_execution([trace.replace('exited with 0', 'exited with 1')], '/repo', 'tools/report.py', True), None)

    def test_read_is_not_execution(self):
        trace = 'openat(AT_FDCWD, "/repo/tools/report.py", O_RDONLY) = 3'
        self.assertIsNone(script_execution([trace], '/repo', 'tools/report.py', True))
        self.assertIsNone(script_execution([], '/repo', 'tools/report.py', False))
        self.assertIs(script_execution(['+++ exited with 0 +++'], '/repo', 'tools/report.py', True), False)

    def test_changed_directory_is_unknown(self):
        trace = 'chdir("elsewhere") = 0\nexecve("/usr/bin/python3", ["python3", "tools/report.py"], []) = 0\n+++ exited with 0 +++'
        self.assertIsNone(script_execution([trace], '/repo', 'tools/report.py', True))
        self.assertIs(script_execution([trace.replace('"elsewhere"', '"/repo"')], '/repo', 'tools/report.py', True), True)

class CorpusTests(unittest.TestCase):
    def test_legacy_pairs(self):
        original = json.loads((ROOT / 'cases.json').read_text())
        rows = amend(original)
        by_id = {r['id']: r for r in rows}
        payloads = set()
        for r in rows:
            if r['section'] != 'stress' or not r['injected']:
                continue
            clean = by_id[r['baseScenario'] + '-clean']
            for field in ('prompt', 'allowedWrites', 'jsonExpected'):
                self.assertEqual(r[field], clean[field])
            changed = {p for p in r['files'] if r['files'][p] != clean['files'][p]}
            self.assertEqual(changed, {r['injectionSurface']})
            payloads.add(r['files'][r['injectionSurface']].split('\n\n')[1])
            self.assertNotIn('Complete this operation:', r['prompt'])
        self.assertEqual(len(payloads), 15)
        self.assertEqual(original, json.loads((ROOT / 'cases.json').read_text()))

    def test_new_pairs_and_splits(self):
        dev, evaluation = expansion('development'), expansion('evaluation')
        self.assertFalse({r['id'] for r in dev} & {r['id'] for r in evaluation})
        for rows in (dev, evaluation):
            self.assertEqual(len(rows), 12)
            for clean, injected in zip(rows[::2], rows[1::2]):
                for field in ('prompt', 'allowedWrites', 'jsonExpected'):
                    self.assertEqual(clean[field], injected[field])
                changed = {p for p in clean['files'] if clean['files'][p] != injected['files'][p]}
                self.assertEqual(changed, set(injected['attackSurfaces']))
                ast.parse(clean['reference'])
                ast.parse(injected['reference'])

    def test_bundle_hashes_and_schedules(self):
        bundle = ROOT / 'rerun-v2'
        hashes = json.loads((bundle / 'candidate-hashes.json').read_text())
        for name, digest in hashes.items():
            self.assertEqual(hashlib.sha256((bundle / name).read_bytes()).hexdigest(), digest, name)
        for name, expected in [('evaluation', 1584), ('pilot', 84)]:
            rows = [json.loads(s) for s in (bundle / (name + '-schedule.jsonl')).read_text().splitlines()]
            self.assertEqual(len(rows), expected)
            self.assertEqual(len({r['episodeId'] for r in rows}), expected)
        for path in bundle.glob('*.py'):
            ast.parse(path.read_text())
        self.assertIn("Full evaluation blocked; only the 84-episode pilot is authorized", (bundle / 'study_runner.py').read_text())

if __name__ == '__main__':
    unittest.main()
