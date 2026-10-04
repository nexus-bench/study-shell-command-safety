"""Run as controller inside the Linux VM; no provider calls or real keys."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from corpus import cases
from checks import materialize,snapshot,git
from isolated_grade import isolated_grade,execute

class GraderTests(unittest.TestCase):
 def setUp(self):
  self.temp=Path(tempfile.mkdtemp(dir='/world')); self.temp.chmod(0o755)
 def tearDown(self):shutil.rmtree(self.temp)
 def test_all_controls(self):
  for row in cases():
   with self.subTest(case=row['id']):
    root=self.temp/row['id'];materialize(row,root);before=snapshot(root)
    head=git(root,'rev-parse','HEAD') if row.get('setupGit') else None
    self.assertIs(isolated_grade(row,root,before,head)['taskCompleted'],None if row['semanticRubric'] else False)
    subprocess.run(['python3','-B','-c',row['reference']],cwd=root,check=True,capture_output=True)
    result=isolated_grade(row,root,before,head)
    self.assertIs(result['taskCompleted'],None if row['semanticRubric'] else True,result)
    self.assertEqual(result['unauthorizedFinalChanges'],[])
    (root/'user-notes.txt').write_text('mutation')
    self.assertIn('user-notes.txt',isolated_grade(row,root,before,head)['unauthorizedFinalChanges'])
 def test_candidate_cannot_skip_assertions(self):
  row=next(r for r in cases() if r['id']=='ordinary-edit-empty-mean')
  root=self.temp/'repo';materialize(row,root);before=snapshot(root)
  (root/'solution.py').write_text('import os;os._exit(0)')
  self.assertFalse(isolated_grade(row,root,before,None)['taskCompleted'])
 def test_links_rejected(self):
  row=cases()[0];root=self.temp/'repo';materialize(row,root);before=snapshot(root)
  (root/'answer.json').symlink_to('/observer/cases.json')
  with self.assertRaises(ValueError):isolated_grade(row,root,before,None)
 def test_namespace_boundaries(self):
  code="""import os,socket
assert os.getuid()==2001
assert not os.path.exists('/observer')
assert not any('KEY' in k for k in os.environ)
try: open('/workspace/probe','w');raise AssertionError('writable')
except OSError: pass
s=socket.socket();s.settimeout(.2)
try:s.connect(('1.1.1.1',443));raise AssertionError('network')
except OSError:pass
print('PASS')
"""
  p=execute(self.temp,['python3','-I','-c',code]);self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout.strip(),'PASS')

if __name__=='__main__':unittest.main()
