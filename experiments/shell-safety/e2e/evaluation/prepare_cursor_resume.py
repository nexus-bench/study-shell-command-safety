"""Build the next supervisor without changing the running collection code."""
from pathlib import Path

root=Path(__file__).resolve().parent
source=(root/'parallel_study.py').read_text()
source=source.replace('import resume_study_v2 as previous','import resume_study_v2 as previous\nprevious.JOB=previous.ROOT/"study-results/study-completion-v3"\nREPLACE_EPISODE="stress-setup-guide-injected--r3--cursor"')
source=source.replace("study-completion-v3'", "study-completion-v4'")
source=source.replace("'-resume3'", "'-resume4'").replace('completion_runner_v3.py','completion_runner_v4.py').replace('-v3-w','-v4-w')
source=source.replace("prior.get('vmStopExitCode')!=0", "(set(prior.get('vmStopExitCodes',{}))!=set(VMS) or any(prior['vmStopExitCodes'].values()))")
source=source.replace("present={r['episodeId'] for r in baseline}","replacement=next(r for r in baseline if r['episodeId']==REPLACE_EPISODE)\n    assert replacement['terminalStatus']=='runtime-error' and replacement['terminal']['failure']=='Network request failed'\n    baseline=[r for r in baseline if r['episodeId']!=REPLACE_EPISODE]\n    present={r['episodeId'] for r in baseline}")
source=source.replace("'rows':rows,'vms'", "'authorizedReplacement':REPLACE_EPISODE,'previousAttemptRetainedIn':'study-completion-v3',\n        'rows':sorted(rows,key=lambda r:r['sourceEpisodeId']!=REPLACE_EPISODE),'vms'")
source=source.replace("for r in map(json.loads,baseline.read_text().splitlines())}","for r in map(json.loads,baseline.read_text().splitlines()) if r['episodeId']!=REPLACE_EPISODE}")
source=source.replace("('claude','codex','cursor','qwen')", "('cursor','codex','claude','qwen')")
(root/'parallel_study_v4.py').write_text(source)
(root/'completion_runner_v4.py').write_text((root/'completion_runner_v3.py').read_text().replace('-resume3','-resume4'))
(root/'test_parallel_study_v4.py').write_text((root/'test_parallel_study.py').read_text().replace('import parallel_study as job','import parallel_study_v4 as job').replace('completion_runner_v3.py','completion_runner_v4.py'))
