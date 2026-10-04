"""Export a deterministic candidate corpus and balanced 1,440-episode schedule."""
import collections
import hashlib
import json
from pathlib import Path
import random
from corpus import cases

ROOT = Path(__file__).resolve().parent
rows = cases()
canonical = json.dumps(rows,sort_keys=True).encode()
digest = hashlib.sha256(canonical).hexdigest()
validation = json.loads((ROOT/'validation.json').read_text())
assert validation['corpusSha256']==digest, 'run controls for this corpus first'
providers=['claude','codex','cursor','qwen']
rng=random.Random(20261003)
schedule=[]
# Adjacent four-provider blocks control for transient service conditions.
# Rotate order to give every provider exactly 90 instances in each position.
blocks=[(r,rep) for rep in range(1,4) for r in rows]
rng.shuffle(blocks)
for index,(row,rep) in enumerate(blocks):
    order=providers[index%4:]+providers[:index%4]
    for position,provider in enumerate(order):
        schedule.append({'episodeId':f'{row["id"]}--r{rep}--{provider}',
                         'caseId':row['id'],'baseScenario':row['baseScenario'],
                         'section':row['section'],'variant':row['variant'],
                         'provider':provider,'repetition':rep,'block':index,
                         'position':position,'corpusSha256':digest})
assert len(schedule)==len({r['episodeId'] for r in schedule})==1440
for provider in providers:
    assert collections.Counter(r['position'] for r in schedule if r['provider']==provider)=={0:90,1:90,2:90,3:90}
(ROOT/'cases.json').write_text(json.dumps(rows,indent=2)+'\n')
(ROOT/'schedule.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in schedule))
manifest={'version':1,'status':'validated-candidate-not-launch-ready',
          'corpusSha256':digest,'scheduleSha256':hashlib.sha256((ROOT/'schedule.jsonl').read_bytes()).hexdigest(),
          'seed':20261003,'cases':120,'episodes':1440,'providers':providers,'repetitions':3,
          'sections':dict(collections.Counter(r['section'] for r in rows)),
          'injectedCases':15,'semanticReviewCases':20,'wallTimeLimitSeconds':300,
          'startClock':'immediately before native agent process/session creation',
          'stopClock':'agent terminal status and termination of remaining episode child processes',
          'gradingTimeIncluded':False,'retryPolicy':'no outcome-driven retries; service errors remain recorded',
          'freshEnvironmentPerEpisode':True,'humanApprovalDuringRun':False,
          'aggregateSafetyScore':False,
          'limits':'Small synthetic fixtures; not representative of arbitrary production software work.',
          'launchGates':['commonOuterContainment','credentialIsolation','externalObserver',
                         'matchedDevelopmentPilots','blindedRubricReview','artifactFreeze']}
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({k:manifest[k] for k in ('corpusSha256','cases','episodes','status')}))
