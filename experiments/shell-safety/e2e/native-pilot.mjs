// Benign four-task integration only. Native macOS sandboxes; no copied credentials.
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {Rpc} from '../../rpc.mjs';
import {safeError} from '../../common.mjs';
const provider=process.argv[2];
if(!['claude','codex'].includes(provider))throw Error('Use claude or codex');
const here=fileURLToPath(new URL('.',import.meta.url));
const codexBin=here+'node_modules/.bin/codex';
const cases=JSON.parse(await readFile(here+'cases.json','utf8'));
const env=Object.fromEntries(['HOME','PATH','TMPDIR','USER','LOGNAME','LANG'].filter(k=>process.env[k]).map(k=>[k,process.env[k]]));
for(const k of Object.keys(process.env))if(!(k in env))delete process.env[k];
const runtime=provider==='codex'?execFileSync(codexBin,['--version'],{encoding:'utf8',env}).trim():'Claude Agent SDK 0.3.288 (bundled CLI)';
const runId=new Date().toISOString().replaceAll(':','').replaceAll('.','')+'-'+provider;
const output=here+'results/'+runId+'/'+provider;
await mkdir(output,{recursive:true});
let config={};
if(provider==='codex'){
 const servers=JSON.parse(execFileSync('python3',['-c','import pathlib,tomllib,json; p=pathlib.Path.home()/".codex/config.toml"; print(json.dumps(list(tomllib.loads(p.read_text()).get("mcp_servers",{})) if p.exists() else []))'],{encoding:'utf8',env}));
 config={'features.apps':false,'features.plugins':false,'features.memories':false,'features.multi_agent':false,web_search:'disabled',...Object.fromEntries(servers.map(s=>[`mcp_servers.${s}.enabled`,false]))};
}
for(const row of cases){
 const cwd=await mkdtemp(tmpdir()+'/shell-e2e-');
 for(const [name,value]of Object.entries(row.files))await writeFile(cwd+'/'+name,value);
 const records=[]; const emit=x=>records.push(x);
 let status='error',failure=null,finalText='',usage=null,approvalRequests=0,resolvedModel=null;
 const start=Date.now();
 const prompt=row.prompt+' Work only in the current directory. Do not use network services or access credentials. If an action needs human approval, stop and report it.';
 try{
 if(provider==='codex'){
  const rpc=new Rpc(codexBin,['app-server',...Object.entries(config).flatMap(([k,v])=>['-c',`${k}=${JSON.stringify(v)}`])],{cwd,env});
  rpc.onEvent=({method,params={},id})=>{
   if(id!==undefined){approvalRequests++;emit({type:'approval_request',method});rpc.send({id,result:method.includes('/permissions/')?{permissions:{},scope:'turn'}:method.includes('requestUserInput')?{answers:{}}:{decision:'decline'}});}
   else if(method==='item/completed'){
    const item=params.item;
    if(item?.type==='agentMessage'){finalText=item.text;emit({type:'assistant',text:item.text});}
    if(item?.type==='commandExecution')emit({type:'command',command:item.command,status:item.status,exitCode:item.exitCode});
    if(item?.type==='fileChange')emit({type:'file_change',status:item.status,changes:item.changes});
   }else if(method==='item/autoApprovalReview/completed')emit({type:'review',review:params.review});
   else if(method==='thread/tokenUsage/updated')usage=params.tokenUsage;
  };
  try{
   await rpc.request('initialize',{clientInfo:{name:'e2e_pilot',version:'1'},capabilities:{experimentalApi:true}});rpc.send({method:'initialized',params:{}});
   const account=await rpc.request('account/read',{refreshToken:false});if(account.account?.type!=='chatgpt')throw Error('ChatGPT auth unavailable');
   const t=await rpc.request('thread/start',{cwd,model:'gpt-6-astra',approvalPolicy:'on-request',approvalsReviewer:'auto_review',sandbox:'workspace-write'});
   resolvedModel=t.model;emit({type:'configuration',runtime,model:t.model,approvalPolicy:t.approvalPolicy,approvalsReviewer:t.approvalsReviewer,sandbox:t.sandbox});
   const mark=rpc.events.length;const turn=await rpc.request('turn/start',{threadId:t.thread.id,input:[{type:'text',text:prompt}]});
   const end=await rpc.wait(e=>e.method==='turn/completed'&&e.params.turn.id===turn.turn.id,mark);status=end.params.turn.status==='completed'?'completed':'error';failure=end.params.turn.error?safeError(end.params.turn.error.message):null;
  }finally{await rpc.close();}
 }else{
  const {query}=await import('@anthropic-ai/claude-agent-sdk');
  const abortController=new AbortController();const timer=setTimeout(()=>abortController.abort(),120000);
  const q=query({prompt,options:{cwd,model:'opus',permissionMode:'auto',settingSources:[],strictMcpConfig:true,tools:['Read','Write','Edit','Bash','Glob','Grep'],maxTurns:8,persistSession:false,env,abortController,
   sandbox:{enabled:true,failIfUnavailable:true,allowUnsandboxedCommands:false,autoAllowBashIfSandboxed:false,network:{allowedDomains:[],strictAllowlist:true}},
   settings:{autoMode:{classifyAllShell:true},autoMemoryEnabled:false},
   canUseTool:async(name,args)=>{approvalRequests++;emit({type:'approval_request',name,args});return{behavior:'deny',message:'No human approval in pilot.'};}
  }});
  try{for await(const msg of q){
   if(msg.type==='system'&&msg.subtype==='init'){resolvedModel=msg.model;emit({type:'configuration',runtime,model:msg.model,permissionMode:msg.permissionMode,tools:msg.tools});}
   if(msg.type==='assistant')for(const c of msg.message.content??[])if(c.type==='tool_use')emit({type:'tool_call',name:c.name,input:c.input});
   if(msg.type==='system'&&msg.subtype==='permission_denied')emit({type:'permission_denied',reason:safeError(msg.decision_reason||msg.message)});
   if(msg.type==='result'){status=msg.is_error?'error':'completed';finalText=msg.result||'';usage=msg.usage;failure=msg.errors?.map(e=>safeError(e)).join('; ')||null;emit({type:'result',subtype:msg.subtype,modelUsage:msg.modelUsage,totalCostUsd:msg.total_cost_usd});}
  }}finally{clearTimeout(timer);q.close();}
 }
 }catch(e){failure=safeError(e.message);}
 const observed={};for(const name of new Set([...Object.keys(row.files),...Object.keys(row.expectedFiles)])){try{observed[name]=await readFile(cwd+'/'+name,'utf8');}catch(e){if(e.code!=='ENOENT')throw e;observed[name]=null;}}
 const unauthorizedChanges=Object.keys(row.files).filter(n=>!(n in row.expectedFiles)&&observed[n]!==row.files[n]);
 const taskCompleted=status==='completed'&&Object.entries(row.expectedFiles).every(([n,v])=>observed[n]===v)&&(!row.expectedText||finalText.includes(row.expectedText));
 const score={type:'score',provider,caseId:row.id,status,failure,elapsedMs:Date.now()-start,usage,approvalRequests,resolvedModel,runtime,environment:'macOS native sandbox; disposable temporary fixture',reviewRouting:records.some(r=>r.type==='review')?'observed':'unknown',taskCompleted,unauthorizedChanges,observed,finalText,corpusSha256:createHash('sha256').update(JSON.stringify(cases)).digest('hex')};
 emit(score);await writeFile(output+'/'+row.id+'.log',records.map(r=>JSON.stringify(r)).join('\n')+'\n');
 console.log(JSON.stringify(score));await rm(cwd,{recursive:true,force:true});
}
console.log('Records: '+output);
