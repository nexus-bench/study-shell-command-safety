"""Generate blinded semantic packets; keep private mapping separate from reviewers."""
import argparse
import hashlib
import json
from pathlib import Path
import random

def export(results,rows,dest):
    dest.mkdir(parents=True,exist_ok=False)
    cases={r['id']:r for r in rows};selected=[r for r in results if cases[r['caseId']].get('semanticRubric')]
    random.Random(20261003).shuffle(selected);mapping={};packets=[]
    for n,r in enumerate(selected,1):
        row=cases[r['caseId']];ident=f'review-{n:04}'
        mapping[ident]=r['episodeId']
        packets.append({'reviewId':ident,'prompt':row['prompt'],'fixtureFacts':row['files'],
          'rubric':row['semanticRubric'],'finalResponse':r.get('terminal',{}).get('finalText',''),
          'finalChanges':r.get('unauthorizedFinalChanges'),
          'observedFixtureEvents':r.get('unauthorizedFixtureEvents'),
          'coverage':r.get('observationCoverage'),
          'reviewerA':None,'reviewerB':None,'adjudication':None})
    (dest/'packets.json').write_text(json.dumps(packets,indent=2)+'\n')
    (dest/'PRIVATE-MAPPING.json').write_text(json.dumps(mapping,indent=2)+'\n')
    (dest/'PRIVATE-MAPPING.json').chmod(0o600)
    return len(packets)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('results',type=Path);p.add_argument('destination',type=Path);a=p.parse_args()
    rows=json.loads((Path(__file__).parent/'cases.json').read_text())
    records=[json.loads(x) for x in a.results.read_text().splitlines() if x.strip()]
    print(export(records,rows,a.destination))
