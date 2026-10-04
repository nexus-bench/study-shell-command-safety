"""Root-owned inference relay. Secrets never enter the CLI environment.

Only fixed inference endpoints are supported. This is not a general HTTP proxy.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

ROUTES = {
    'qwen': ('openrouter.ai', '/api/v1', {'/chat/completions'}, 'OPENROUTER_API_KEY'),
    'claude': ('api.anthropic.com', '', {'/v1/messages','/v1/messages/count_tokens'}, 'ANTHROPIC_API_KEY'),
    'codex': ('api.openai.com', '/v1', {'/responses','/responses/compact'}, 'OPENAI_API_KEY'),
}


def start_broker(keys, max_requests=64):
    counts=[]
    lock=threading.Lock()
    attempts=0
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.0'
        def log_message(self,*args): pass
        def do_POST(self):
            nonlocal attempts
            parts=self.path.split('/',2)
            provider=parts[1] if len(parts)>2 else ''
            if provider not in ROUTES:
                self.send_error(404); return
            host,prefix,allowed,keyname=ROUTES[provider]
            path='/'+parts[2]
            if path.split('?',1)[0] not in allowed or not keys.get(keyname):
                self.send_error(403); return
            with lock:
                if attempts>=max_requests:
                    self.send_error(429); return
                attempts+=1
            self.connection.settimeout(10)
            try: length=int(self.headers.get('Content-Length','0'))
            except ValueError: self.send_error(400); return
            if length<=0 or length>8*1024*1024:
                self.send_error(413); return
            body=self.rfile.read(length)
            headers={k:v for k,v in self.headers.items() if k.lower() in
                     ('content-type','content-encoding','accept','anthropic-version','anthropic-beta','openai-beta','originator','user-agent')}
            if provider=='claude': headers['x-api-key']=keys[keyname]
            else: headers['Authorization']='Bearer '+keys[keyname]
            connection=http.client.HTTPSConnection(host,timeout=180)
            try:
                connection.request('POST',prefix+path,body=body,headers=headers)
                response=connection.getresponse()
                counts.append({'provider':provider,'path':path.split('?',1)[0],'status':response.status})
                self.send_response(response.status)
                self.send_header('Content-Type',response.getheader('Content-Type','application/json'))
                self.end_headers()
                while chunk:=response.read1(65536):
                    self.wfile.write(chunk); self.wfile.flush()
            except (OSError,http.client.HTTPException):
                counts.append({'provider':provider,'transportError':True})
            finally: connection.close()
    server=ThreadingHTTPServer(('127.0.0.1',19001),Handler)
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    return server,counts
