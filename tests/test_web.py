import tempfile,threading,unittest,http.client,json
from pathlib import Path
from panel.web import WebServer,Auth
class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.auth=Auth(Path(self.tmp.name)/'admin.db')
        self.auth.bootstrap('Admin','examplePass123')
        self.server=WebServer(('127.0.0.1',0),self.auth,lambda r:{'action':r['action']})
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.port=self.server.server_port
    def tearDown(self): self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def call(self,path,method='GET',body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.port);h={'Content-Type':'application/json',**(headers or {})};c.request(method,path,json.dumps(body) if body is not None else None,h);r=c.getresponse();data=r.read();hs=dict(r.getheaders());c.close();return r.status,hs,json.loads(data)
    def login(self):
        status,h,b=self.call('/api/login','POST',{'username':'Admin','password':'examplePass123'});self.assertEqual(status,200)
        return {'Cookie':h['Set-Cookie'].split(';')[0],'X-CSRF-Token':b['csrf']}
    def test_auth_required(self): self.assertEqual(self.call('/api/snapshot')[0],401)
    def test_csrf_required(self):
        h=self.login();h.pop('X-CSRF-Token');self.assertEqual(self.call('/api/action','POST',{'action':'service'},h)[0],403)
    def test_valid_action(self):
        h=self.login();self.assertEqual(self.call('/api/action','POST',{'action':'users'},h)[0],200)
    def test_password_change_invalidates_sessions(self):
        h=self.login();self.assertEqual(self.call('/api/password','POST',{'current':'examplePass123','password':'newExamplePass123'},h)[0],200)
        self.assertEqual(self.call('/api/snapshot',headers=h)[0],401)
    def test_bad_credentials(self): self.assertEqual(self.call('/api/login','POST',{'username':'Admin','password':'wrong'})[0],401)
    def test_login_brute_force_limit(self):
        for _ in range(8): self.call('/api/login','POST',{'username':'Admin','password':'wrong'})
        self.assertEqual(self.call('/api/login','POST',{'username':'Admin','password':'wrong'})[0],429)
    def test_cookie_flags(self):
        _,h,_=self.call('/api/login','POST',{'username':'Admin','password':'examplePass123'})
        self.assertIn('HttpOnly',h['Set-Cookie']);self.assertIn('Secure',h['Set-Cookie']);self.assertIn('SameSite=Strict',h['Set-Cookie'])
