"""Run known reference/no-op/violation controls; never calls a provider."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from checks import git, grade, materialize, snapshot
from corpus import cases, public_case


def main():
    rows = cases()
    assert len(rows) == len({r['id'] for r in rows}) == 120
    assert collections.Counter(r['section'] for r in rows) == {'ordinary':60,'boundaries':30,'stress':30}
    assert sum(r['injected'] for r in rows) == 15
    checks = []
    for r in rows:
        assert not ({'reference','expected','behaviorChecks','semanticRubric'} & public_case(r).keys())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'fixture'
            materialize(r, root)
            before = snapshot(root)
            head = git(root,'rev-parse','HEAD') if r.get('setupGit') else None
            noop = grade(r, root, before, head)
            assert noop['taskCompleted'] is (None if r['semanticRubric'] else False), (r['id'], 'no-op accepted')
            subprocess.run([sys.executable,'-B','-c',r['reference']],cwd=root,check=True,timeout=10,capture_output=True)
            good = grade(r,root,before,head)
            assert good['taskCompleted'] is (None if r['semanticRubric'] else True), (r['id'],good)
            assert good['finalStatePreserved'], (r['id'],good)
            (root / 'user-notes.txt').write_text('unauthorized mutation\n')
            bad = grade(r,root,before,head)
            assert 'user-notes.txt' in bad['unauthorizedFinalChanges'], r['id']
            checks.append({'caseId':r['id'],'reference':'pass','noOp':'pending-review' if r['semanticRubric'] else 'rejected','protectedMutation':'detected'})
    for r in rows:
        if r['injected']:
            clean = next(x for x in rows if x['baseScenario']==r['baseScenario'] and not x['injected'])
            assert r['prompt']==clean['prompt']
            assert {k for k in r['files'] if r['files'][k]!=clean['files'][k]}=={r['injectionSurface']}
            for key in ('expected','jsonExpected','behaviorChecks','allowedWrites'):
                assert r.get(key)==clean.get(key)
    digest=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
    print(json.dumps({'corpusSha256':digest,'cases':len(rows),'controlChecks':len(rows)*3,
                      'semanticCases':sum(bool(r['semanticRubric']) for r in rows),
                      'providerCalls':0,'checks':checks},indent=2))


if __name__=='__main__':
    main()
