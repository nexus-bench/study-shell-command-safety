import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import freeze

class FreezeTests(unittest.TestCase):
 def test_modified_bytes_reject_launch(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'runner.py';p.write_text('original')
   (root/'freeze.json').write_text(json.dumps({'files':[{'source':'runner.py','deployed':'runner.py','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}]}))
   with patch.object(freeze,'ROOT',root):
    freeze.verify();p.write_text('changed')
    with self.assertRaises(ValueError):freeze.verify()
