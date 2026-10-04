"""Read archived pilot JSON directly; never extracts or executes archive contents."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
import tarfile

folder = Path(sys.argv[1])
rows = []
with tarfile.open(folder / 'vm-artifacts.tar') as archive:
    for member in archive:
        if member.isfile() and member.name.endswith('.json'):
            with archive.extractfile(member) as f:
                row = json.load(f)
            if 'episodeId' in row and 'terminalStatus' in row:
                rows.append(row)
counts = defaultdict(Counter)
findings = []
for r in rows:
    c = counts[r['provider']]; c['episodes'] += 1
    c['taskPass' if r['taskCompleted'] is True else 'taskFail' if r['taskCompleted'] is False else 'taskUnresolved'] += 1
    c['terminal:' + r['terminalStatus']] += 1
    if r.get('unauthorizedEffectsObserved') is True: c['effectEpisodes'] += 1
    if r.get('unauthorizedEffectsObserved') is None: c['effectUnknown'] += 1
    for k in ('gradingError', 'credentialLeakDetected', 'runtimeError'):
        if r.get(k): c[k] += 1
    if r.get('requiredScript') or r.get('executionObservations'):
        for name, value in r.get('executionObservations', {}).items():
            c[name + ':' + str(value)] += 1
    if r['taskCompleted'] is not True or r.get('unauthorizedEffectsObserved') is not False:
        findings.append({k: r.get(k) for k in ('episodeId','provider','taskCompleted','terminalStatus',
            'outcomeFailures','unresolvedObservations','unauthorizedEffectsObserved','effectCategories',
            'gradingError','runtimeError','observationCoverage','executionObservations')})
bundle = Path(sys.argv[2]) if len(sys.argv)>2 else Path(__file__).parent/'rerun-v2'
expected = {json.loads(s)['episodeId'] for s in (bundle/'pilot-schedule.jsonl').read_text().splitlines()}
seen = Counter(r['episodeId'] for r in rows)
result = {'expected': len(expected), 'completedRecords': len(rows), 'missing': sorted(expected-set(seen)),
          'extra': sorted(set(seen)-expected), 'duplicates': [k for k,v in seen.items() if v>1],
          'byProvider': dict(counts), 'findings': findings,
          'semanticReview': 'unchanged; unresolved semantic cases require review',
          'fullEvaluationStarted': False}
(folder/'pilot-summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='findings'},indent=2))
