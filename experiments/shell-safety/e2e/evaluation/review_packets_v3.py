"""Blinded review packet preparation; does not supply reviewer judgments."""
import json
from pathlib import Path
import random

def export(results, rows, dest):
    dest=Path(dest); dest.mkdir(parents=True,exist_ok=False)
    cases={r['id']:r for r in rows}
    selected=[r for r in results if cases[r['caseId']].get('semanticRubric') or cases[r['caseId']].get('observationRequirements')]
    random.Random(20261004).shuffle(selected)
    packets=[]; private={}
    for n,r in enumerate(selected,1):
        ident=f'review-{n:04d}'; case=cases[r['caseId']]
        private[ident]={'episodeId':r['episodeId'],'artifacts':r.get('artifacts'),
                        'events':r.get('events'), 'provider':r.get('provider')}
        packet={'reviewId':ident,'prompt':case['prompt'],'fixtureFacts':case['files'],
            'semanticRubric':case.get('semanticRubric'),'actionRequirements':case.get('observationRequirements',[]),
            'finalResponse':r.get('terminal',{}).get('finalText',''),
            'finalChanges':r.get('unauthorizedFinalChanges'),
            'observedFixtureEvents':r.get('unauthorizedFixtureEvents'),
            'coverage':r.get('observationCoverage'),'actionEvidence':r.get('actionReview',{}),
            'reviewerA':None,'reviewerB':None,'adjudication':None,
            'evidenceAccess':'Trace indexes and line numbers refer to archived raw traces in the private mapping. Request expanded evidence by reviewId; never infer absence from zero scanner hits.',
            'blindingLimit':'Explicit provider IDs and episode paths removed; prose or tool syntax may still reveal product identity.'}
        # Preserve original evidence in private archive; normalize only episode identity.
        packet=json.loads(json.dumps(packet).replace(r['episodeId'],'EPISODE'))
        packets.append(packet)
    (dest/'packets.json').write_text(json.dumps(packets,indent=2)+'\n')
    (dest/'PRIVATE-MAPPING.json').write_text(json.dumps(private,indent=2)+'\n')
    (dest/'PRIVATE-MAPPING.json').chmod(0o600)
    return len(packets)
