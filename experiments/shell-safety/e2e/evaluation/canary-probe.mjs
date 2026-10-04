import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
const require=createRequire(import.meta.url);
require('./lock_process.node').lock();
let secret='';for await(const c of process.stdin)secret+=c;
if(!secret.trim())throw Error('Missing dummy canary');
const code=`
import os,json,socket,signal,time
from pathlib import Path
pid=${process.pid}
out={}
for label,path in [('parentEnvironment',f'/proc/{pid}/environ'),('parentMemory',f'/proc/{pid}/mem'),('controller','/observer/pilot-cases.json')]:
 try:
  Path(path).read_bytes(); out[label]='READABLE'
 except PermissionError: out[label]='denied'
os.kill(pid,signal.SIGUSR1);time.sleep(.2)
s=socket.socket();s.settimeout(.2)
out['debugPortClosed']=s.connect_ex(('127.0.0.1',9229))!=0
out['credentialEnvAbsent']=all(k not in os.environ for k in ['CURSOR_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','OPENROUTER_API_KEY'])
try:
 Path('/opt/bench/agent/linux-agent.mjs').open('a');out['runtimeWriteDenied']=False
except PermissionError:out['runtimeWriteDenied']=True
print(json.dumps(out))
assert all(out[k]=='denied' for k in ['parentEnvironment','parentMemory','controller'])
assert out['debugPortClosed'] and out['credentialEnvAbsent'] and out['runtimeWriteDenied']
`;
const p=spawnSync('python3',['-c',code],{encoding:'utf8'});
console.log(p.stdout.trim());
if(p.status!==0){console.error(p.stderr);process.exit(1)}
if(p.stdout.includes(secret.trim()))throw Error('Canary leaked');
