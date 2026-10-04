"""Validate all archived records and create a factual evidence index, not semantic grades."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import tarfile

def main():
    folder=Path(sys.argv[1]); records=[]
    with tarfile.open(folder/'vm-artifacts.tar') as archive:
        for member in archive:
            if member.isfile() and member.name.endswith('.json'):
                row=json.load(archive.extractfile(member))
                if 'episodeId' in row and 'terminalStatus' in row: records.append(row)
    by_case={r['id']:r for r in json.loads((Path(__file__).parent/'rerun-v3/development-cases.json').read_text())}
    issues=[]; index=[]; action_count=0; scripts=Counter()
    for row in records:
        case=by_case[row['caseId']]
        required=case.get('observationRequirements',[])
        for key in required:
            packet=row.get('actionReview',{}).get(key)
            if not packet or packet.get('satisfied') is not None or packet.get('reviewRequired') is not True:
                issues.append(row['episodeId']+':action-review-schema')
            else: action_count+=1
            if key not in row.get('unresolvedObservations',[]): issues.append(row['episodeId']+':lost-unknown')
        if case.get('requiredScript') or case['family']=='builds':
            evidence=row.get('executionObservations',{}).get('required-script-executed')
            scripts[str(evidence)]+=1
            if evidence is None: issues.append(row['episodeId']+':script-observation-unknown')
        if row.get('gradingError') or row.get('runtimeError') or row.get('credentialLeakDetected'):
            issues.append(row['episodeId']+':infrastructure-or-grading')
        if row.get('terminalStatus')!='completed': issues.append(row['episodeId']+':terminal-'+str(row.get('terminalStatus')))
        index.append({k:row.get(k) for k in ('episodeId','caseId','provider','taskCompleted','outcomeFailures',
            'unresolvedObservations','effectCategories','unauthorizedEffectsObserved','executionObservations',
            'actionReview','terminal','observationComplete','observationCoverage')})
    if action_count!=24: issues.append('expected-24-action-review-packets')
    if len(records)!=76: issues.append('expected-76-records')
    report={'recordCount':len(records),'measurementReady':not issues,'issues':issues,
        'actionReviewPackets':action_count,'scriptEvidence':dict(scripts),
        'taskLabels':dict(Counter(str(r['taskCompleted']) for r in records)),
        'effectEpisodesByProvider':dict(Counter(r['provider'] for r in records if r.get('unauthorizedEffectsObserved') is True)),
        'scope':'Pilot measurement validation; not independent blinded semantic/action adjudication.',
        'archiveSha256':hashlib.sha256((folder/'vm-artifacts.tar').read_bytes()).hexdigest(),
        'fullEvaluationStarted':False,'records':index}
    (folder/'pilot-review.json').write_text(json.dumps(report,indent=2)+'\n')
    from review_packets_v3 import export
    packet_dir=folder/'review-packets'
    if not packet_dir.exists(): export(records,list(by_case.values()),packet_dir)
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))

if __name__=='__main__':main()
