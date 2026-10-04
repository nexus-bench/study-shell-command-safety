// Development pilots only. Native provider tool loops; no custom tool executor.
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {Rpc} from './rpc.mjs';
const require=createRequire(import.meta.url);
require('./lock_process.node').lock();
let input='';for await(const c of process.stdin)input+=c;
const request=JSON.parse(input);input='';
const {provider,prompt,cwd}=request;
const emit=x=>console.log(JSON.stringify(x,(_,v)=>typeof v==='bigint'?String(v):v));
let finalText='',status='error',failure=null;
const env={...process.env};
const timeout=setTimeout(()=>{emit({type:'terminal',status:'timeout'});process.exit(3)},request.wallTimeMs||120000);
try {
 if(provider==='qwen') {
  const {query}=await import('@qwen-code/sdk');
  const run=query({prompt,options:{cwd,authType:'openai',model:'qwen/qwen3-coder-plus',permissionMode:'auto',maxSessionTurns:64,
   env:{...env,OPENAI_API_KEY:'benchmark-placeholder',OPENAI_BASE_URL:'http://127.0.0.1:19001/qwen',QWEN_AUTH_TYPE:'openai'},
   canUseTool:async()=>({behavior:'deny',message:'No human approvals in this pilot.'})}});
  try{for await(const event of run){emit({type:'event',event});if(event.type==='result'){status=event.is_error?'error':'completed';finalText=event.result||'';}}}finally{await run.close()}
 }else if(provider==='claude') {
  const {query}=await import('@anthropic-ai/claude-agent-sdk');
  const run=query({prompt,options:{cwd,model:'claude-opus-5-5',permissionMode:'auto',settingSources:[],strictMcpConfig:true,
   tools:['Read','Write','Edit','Bash','Glob','Grep'],maxTurns:64,persistSession:false,
   env:{...env,ANTHROPIC_API_KEY:'benchmark-placeholder',ANTHROPIC_BASE_URL:'http://127.0.0.1:19001/claude'},
   sandbox:{enabled:true,failIfUnavailable:true,allowUnsandboxedCommands:false,autoAllowBashIfSandboxed:false,
    network:{allowedDomains:[],strictAllowlist:true}},
   settings:{autoMode:{classifyAllShell:true},autoMemoryEnabled:false},
   canUseTool:async()=>({behavior:'deny',message:'No human approvals in this pilot.'})}});
  try{for await(const event of run){emit({type:'event',event});if(event.type==='result'){status=event.is_error?'error':'completed';finalText=event.result||'';}}}finally{run.close()}
 }else if(provider==='cursor') {
  const {Agent}=await import('@cursor/sdk');
  const agent=await Agent.create({apiKey:request.cursorKey,model:{id:'composer-2.5',params:[{id:'fast',value:'true'}]},
   tools:['shell','read','edit','grep','glob','ls','delete'],
   local:{cwd,autoReview:true,settingSources:[],sandboxOptions:{enabled:true},enableAgentRetries:false}});
  delete request.cursorKey;
  try{const run=await agent.send(prompt);for await(const event of run.stream())emit({type:'event',event});const result=await run.wait();emit({type:'result',result});status=result.status==='finished'?'completed':'error';finalText=result.result||'';}finally{await agent[Symbol.asyncDispose]()}
 }else if(provider==='codex') {
  const config={model_provider:'benchmark', 'model_providers.benchmark.name':'benchmark',
   'model_providers.benchmark.base_url':'http://127.0.0.1:19001/codex',
   'model_providers.benchmark.env_key':'BENCHMARK_TOKEN','model_providers.benchmark.wire_api':'responses',
   'model_providers.benchmark.requires_openai_auth':false,'model_providers.benchmark.supports_websockets':false,
   'features.apps':false,'features.plugins':false,'features.memories':false,'features.multi_agent':false,web_search:'disabled'};
  const rpc=new Rpc('/opt/bench/node_modules/.bin/codex',['app-server',...Object.entries(config).flatMap(([k,v])=>['-c',`${k}=${JSON.stringify(v)}`])],{cwd,env:{...env,BENCHMARK_TOKEN:'benchmark-placeholder'}});
  rpc.onEvent=event=>{
   emit({type:'event',event});
   if(event.id!==undefined)rpc.send({id:event.id,result:event.method.includes('/permissions/')?{permissions:{},scope:'turn'}:event.method.includes('requestUserInput')?{answers:{}}:{decision:'decline'}});
   if(event.method==='item/completed'&&event.params.item.type==='agentMessage')finalText=event.params.item.text;
  };
  try{
   await rpc.request('initialize',{clientInfo:{name:'shell_bench_linux_pilot',version:'1'},capabilities:{experimentalApi:true}});rpc.send({method:'initialized',params:{}});
   const thread=await rpc.request('thread/start',{cwd,model:'gpt-6-astra',approvalPolicy:'on-request',approvalsReviewer:'auto_review',sandbox:'workspace-write'});emit({type:'configuration',thread});
   const mark=rpc.events.length;const turn=await rpc.request('turn/start',{threadId:thread.thread.id,input:[{type:'text',text:prompt}]});
   const done=await rpc.wait(e=>e.method==='turn/completed'&&e.params.turn.id===turn.turn.id,mark);
   status=done.params.turn.status==='completed'?'completed':'error';failure=done.params.turn.error||null;
  }finally{await rpc.close()}
 }else throw Error('Unknown provider');
}catch(error){failure=String(error.message)}finally{clearTimeout(timeout)}
emit({type:'terminal',provider,status,finalText,failure});
