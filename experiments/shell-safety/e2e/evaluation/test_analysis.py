import unittest
from analyze import summarize


class AnalysisTests(unittest.TestCase):
    def test_unknown_is_not_success(self):
        s=[dict(episodeId='x',section='boundaries',variant='ambiguous',provider='a',corpusSha256='h',caseId='c',baseScenario='b',repetition=1)]
        r=[dict(episodeId='x',corpusSha256='h',terminalStatus='clarification',taskCompleted=None,unauthorizedEffectsObserved=None)]
        out=summarize(r,s)['summaries'][0]
        self.assertEqual(out['completionKnown'],0)
        self.assertIsNone(out['completionRateAmongKnown'])
        self.assertEqual(out['effectKnown'],0)

    def test_paired_cluster_unit_is_base(self):
        s=[]; r=[]
        for base in range(2):
            for rep in range(3):
                for provider in ('a','b'):
                    eid=f'{base}-{rep}-{provider}'
                    s.append(dict(episodeId=eid,section='ordinary',variant='clean',provider=provider,corpusSha256='h',caseId=str(base),baseScenario=str(base),repetition=rep))
                    r.append(dict(episodeId=eid,corpusSha256='h',terminalStatus='completed',taskCompleted=provider=='a',unauthorizedEffectsObserved=False))
        out=summarize(r,s)['pairedCompletionComparisons'][0]
        self.assertEqual(out['completeBaseScenarios'],2)
        self.assertEqual(out['difference'],1)
        self.assertEqual(out['exploratory95PercentileInterval'],[1,1])
        with self.assertRaises(ValueError):
            summarize(r+[r[0]],s)


if __name__=='__main__':
    unittest.main()
