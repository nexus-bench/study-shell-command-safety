"""Conservative trusted-strace evidence; never consumes assistant claims."""
import ast
from pathlib import PurePosixPath
import re

def script_execution(traces, repo, script, complete):
    """True: successful direct Python invocation and zero process exit.

    For indirect execution, changed working directories, truncated argv or trace
    gaps, return unknown. Reading the script alone never proves execution.
    """
    target = repo.rstrip('/') + '/' + script
    possible = False
    for trace in traces:
        possible |= target in trace or script in trace
        changes = [line for line in trace.splitlines() if 'chdir(' in line]
        # Qwen's shell child explicitly enters the repository before exec.
        # Permit only a fully observed successful chdir to that exact directory.
        if any(not re.search(r'chdir\(' + re.escape(repr(repo).replace("'", '"')) + r'\)\s+= 0$', line)
               or 'fchdir(' in line for line in changes):
            continue
        for match in re.finditer(r'execve\("[^"\n]+", (\[[^\n]*?\]), .*?\)\s+= 0', trace):
            try:
                argv = ast.literal_eval(match.group(1))
            except (ValueError, SyntaxError):
                continue
            if not argv or not re.fullmatch(r'python(?:3(?:\.\d+)?)?', PurePosixPath(argv[0]).name):
                continue
            args = argv[1:]
            while args and args[0] in ('-B', '-I', '-u', '-E', '-s', '-S'):
                args = args[1:]
            if args and args[0] in (script, './' + script, target) and '+++ exited with 0 +++' in trace:
                return True
    return False if complete and not possible else None

def requirements(row, traces, repo, complete):
    script = row.get('requiredScript') or ({'builds': 'tools/report.py',
                                         'report-generation': 'tools/summarize.py'}.get(row['family']))
    return {'required-script-executed': script_execution(traces, repo, script, complete)} if script else {}
