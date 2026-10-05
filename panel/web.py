"""Unprivileged, loopback-only API behind Nginx HTTPS."""
import hashlib,hmac,json,mimetypes,os,secrets,socket,sqlite3,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit
from .common import hash_password,verify_password,username,load_config
STATIC=Path(__file__).parent/'static'
class Auth:
    def __init__(self,path):
        self.path=str(path)
        with self.db() as d: d.executescript('CREATE TABLE IF NOT EXISTS admin(name TEXT,password TEXT); CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,csrf TEXT,expires REAL); CREATE TABLE IF NOT EXISTS attempts(ip TEXT,at REAL);')
    def db(self): return sqlite3.connect(self.path,timeout=15)
    def bootstrap(self,name,password):
        with self.db() as d:
            if not d.execute('SELECT 1 FROM admin').fetchone(): d.execute('INSERT INTO admin VALUES(?,?)',(username(name),hash_password(password)))
    def login(self,name,password,ip):
        now=time.time()
        with self.db() as d:
            d.execute('DELETE FROM attempts WHERE at<?',(now-600,));d.execute('DELETE FROM sessions WHERE expires<?',(now,))
            if d.execute('SELECT COUNT(*) FROM attempts WHERE ip=?',(ip,)).fetchone()[0]>=8: raise PermissionError('Too many login attempts. Try again in 10 minutes.')
            d.execute('INSERT INTO attempts VALUES(?,?)',(ip,now));admin=d.execute('SELECT name,password FROM admin').fetchone()
        if not admin or not verify_password(password,admin[1]) or not hmac.compare_digest(str(name),admin[0]): return None
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        with self.db() as d:
            d.execute('DELETE FROM attempts WHERE ip=?',(ip,));d.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),csrf,now+43200))
        return token,csrf
    def session(self,token):
        with self.db() as d: row=d.execute('SELECT csrf FROM sessions WHERE token=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return row[0] if row else None
    def logout(self,token):
        with self.db() as d: d.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))
    def change(self,current,password):
        with self.db() as d:
            row=d.execute('SELECT password FROM admin').fetchone()
            if not row or not verify_password(current,row[0]): raise ValueError('Current password is incorrect.')
            d.execute('UPDATE admin SET password=?',(hash_password(password),));d.execute('DELETE FROM sessions')

def agent_call(path,request):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
        s.settimeout(20);s.connect(path);s.sendall((json.dumps(request)+'\n').encode());data=b''
        while not data.endswith(b'\n'):
            chunk=s.recv(65536)
            if not chunk: raise RuntimeError('Agent closed connection.')
            data+=chunk
            if len(data)>4*1024*1024: raise RuntimeError('Agent response too large.')
        result=json.loads(data)
        if not result['ok']: raise ValueError(result['error'])
        return result['data']

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,fmt,*args): pass
    def token(self):
        try:
            c=SimpleCookie();c.load(self.headers.get('Cookie',''));return c['vpn_session'].value if 'vpn_session' in c else ''
        except Exception: return ''
    def reply(self,status,data,ctype='application/json',extra=None):
        raw=data if isinstance(data,bytes) else json.dumps(data).encode()
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.end_headers();self.wfile.write(raw)
    def body(self):
        try: size=int(self.headers.get('Content-Length','0'))
        except ValueError: raise ValueError('Invalid content length.')
        if not 0<size<=65536: raise ValueError('JSON body must be 1–65536 bytes.')
        if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('JSON content type required.')
        data=json.loads(self.rfile.read(size))
        if not isinstance(data,dict): raise ValueError('JSON object required.')
        return data
    def authenticated(self,write=False):
        csrf=self.server.auth.session(self.token())
        if not csrf: self.reply(401,{'error':'Please sign in.'});return False
        if write and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),csrf): self.reply(403,{'error':'Invalid CSRF token.'});return False
        return csrf
    def do_GET(self):
        path=urlsplit(self.path).path
        try:
            if path=='/' or path in ('/app.js','/style.css'):
                name='index.html' if path=='/' else path[1:];raw=(STATIC/name).read_bytes();ctype=mimetypes.guess_type(name)[0] or 'text/plain'
                self.reply(200,raw,ctype+'; charset=utf-8');return
            csrf=self.authenticated()
            if not csrf:return
            if path=='/api/me':self.reply(200,{'csrf':csrf});return
            if path=='/api/stream':self.stream();return
            actions={'/api/snapshot':'snapshot','/api/users':'users','/api/events':'events','/api/jobs':'jobs'}
            if path in actions:self.reply(200,self.server.rpc({'action':actions[path]}));return
            self.reply(404,{'error':'Not found.'})
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as e:self.reply(503,{'error':str(e)[:500]})
    def do_POST(self):
        path=urlsplit(self.path).path
        try:
            data=self.body()
            if path=='/api/login':
                result=self.server.auth.login(data.get('username',''),data.get('password',''),self.headers.get('X-Real-IP',self.client_address[0]))
                if not result:self.reply(401,{'error':'Username or password is incorrect.'});return
                token,csrf=result;self.reply(200,{'csrf':csrf},extra={'Set-Cookie':f'vpn_session={token}; Path=/; Max-Age=43200; Secure; HttpOnly; SameSite=Strict'});return
            if not self.authenticated(True):return
            if path=='/api/logout':
                self.server.auth.logout(self.token());self.reply(200,{'ok':True},extra={'Set-Cookie':'vpn_session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Strict'});return
            if path=='/api/password':self.server.auth.change(data.get('current',''),data.get('password',''));self.reply(200,{'ok':True});return
            if path=='/api/action':
                allowed={'save_user','delete_user','service','disconnect','session_speed','domain','settings','export','logs','users'}
                if data.get('action') not in allowed:raise ValueError('Unsupported action.')
                self.reply(200,self.server.rpc(data));return
            self.reply(404,{'error':'Not found.'})
        except PermissionError as e:self.reply(429,{'error':str(e)})
        except (ValueError,KeyError,TypeError) as e:self.reply(400,{'error':str(e)[:500]})
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as e:self.reply(503,{'error':str(e)[:500]})
    def stream(self):
        if not self.server.stream_slots.acquire(False):self.reply(429,{'error':'Too many streams.'});return
        try:
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-cache');self.send_header('X-Accel-Buffering','no');self.send_header('Connection','close');self.end_headers()
            deadline=time.time()+50
            while time.time()<deadline:
                if not self.server.auth.session(self.token()):break
                try: snapshot=self.server.rpc({'action':'snapshot'})
                except Exception as e:snapshot={'ready':False,'error':str(e),'sampled_at':None}
                self.wfile.write(('data: '+json.dumps(snapshot)+'\n\n').encode());self.wfile.flush();time.sleep(2)
        except (BrokenPipeError,ConnectionResetError):pass
        finally:self.server.stream_slots.release();self.close_connection=True
class WebServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,auth,rpc):self.auth=auth;self.rpc=rpc;self.stream_slots=threading.BoundedSemaphore(20);super().__init__(address,Handler)
def main():
    cfg=load_config();auth=Auth(os.environ.get('VPN_PANEL_WEB_DB','/var/lib/vpn-panel-web/admin.db'))
    WebServer(('127.0.0.1',9080),auth,lambda request:agent_call(cfg['socket'],request)).serve_forever()
if __name__=='__main__':main()
