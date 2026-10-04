"""Additive post-study reporting; never rewrites primary episode labels."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from rubric_v2 import effect_breakdown

def build(path):
    counts = defaultdict(Counter)
    episodes = []
    with Path(path).open() as f:
        for line in f:
            r = json.loads(line)
            b = effect_breakdown(r['before'], r['after'], r['unauthorizedFinalChanges'],
                                 r['unauthorizedFixtureEvents'])
            if not any(b.values()):
                continue
            for k, v in b.items():
                if v:
                    counts[r['provider']][k] += 1
            episodes.append({'episodeId': r['episodeId'], 'provider': r['provider'], **b})
    return {'interpretation': 'Episode counts per category overlap. Additions are reported separately; no automatic authorization or harm inference. Original labels unchanged.',
            'byProvider': dict(counts), 'flaggedEpisodes': len(episodes), 'episodes': episodes}

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('results'); p.add_argument('output')
    a = p.parse_args()
    report = build(a.results)
    with Path(a.output).open('x') as f:
        f.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'episodes'}, indent=2))
