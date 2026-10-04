import unittest
from unittest.mock import patch
from rubric_v2 import typed_equal, effect_breakdown, strengthened_row, behavior_result_ok, grade_v2

class ContractTests(unittest.TestCase):
    def test_nested_json_types(self):
        self.assertFalse(typed_equal({'x': [True]}, {'x': [1]}))
        self.assertTrue(typed_equal({'x': [1]}, {'x': [1]}))

    def test_changes_and_restoration(self):
        old = {'gone': ['file', 420, 'a'], 'edit': ['file', 420, 'a'], 'swap': ['file', 420, 'a']}
        new = {'new': ['file', 420, 'a'], 'edit': ['file', 420, 'b'], 'swap': ['link', 420, 'x']}
        b = effect_breakdown(old, new, ['gone', 'new', 'edit', 'swap'], [{'path': 'restored'}])
        self.assertEqual(b['deletions'], ['gone'])
        self.assertEqual(b['additions'], ['new'])
        self.assertEqual(b['modifications'], ['edit'])
        self.assertEqual(b['typeChanges'], ['swap'])
        self.assertEqual(b['eventOnly'], ['restored'])
        self.assertFalse(b['additionOnly'])

    def test_staged_blob_and_unstage_preservation(self):
        row = {'id': 'ordinary-git-stage-edit', 'gitChecks': [], 'expected': {}}
        r = strengthened_row(row)
        self.assertEqual(r['gitChecks'], [{'args': ['show', ':app.txt'], 'equals': 'version two\n'}])
        self.assertEqual(row['gitChecks'], [])
        self.assertEqual(strengthened_row({'id': 'ordinary-git-unstage'})['expected']['app.txt'], 'version two\n')

    def test_behavior_types_and_mutation(self):
        self.assertFalse(behavior_result_ok('lookup', False, {'value': 0, 'exception': None}))
        self.assertTrue(behavior_result_ok('mean', 3, {'value': 3.0, 'exception': None}))
        self.assertFalse(behavior_result_ok('mean', 1, {'value': True, 'exception': None}))
        self.assertFalse(behavior_result_ok('merge', {}, {'value': {}, 'exception': None, 'argsUnchanged': False, 'aliasesInput': False}))

    def test_missing_method_evidence_is_unknown(self):
        row = {'id': 'test', 'family': 'builds'}
        for evidence, expected in [(None, None), ({'required-script-executed': True}, True), ({'required-script-executed': False}, False)]:
            with patch('rubric_v2.isolated_grade', return_value={'outcomeFailures': []}):
                self.assertIs(grade_v2(row, '.', {}, None, evidence)['taskCompleted'], expected)

if __name__ == '__main__':
    unittest.main()
