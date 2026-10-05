import tempfile, unittest
from pathlib import Path
from panel.common import hash_password, verify_password, username, hostname
from panel.state import State

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.s=State(Path(self.tmp.name)/'state.db')
    def tearDown(self): self.tmp.cleanup()
    def test_password_hash_salted(self):
        a=hash_password('secret123!'); self.assertNotEqual(a,hash_password('secret123!'))
        self.assertTrue(verify_password('secret123!',a)); self.assertFalse(verify_password('wrong',a))
        self.assertFalse(verify_password('x','broken'))
    def test_validation(self):
        self.assertEqual(username('Easin'),'Easin'); self.assertEqual(hostname('vpn.example.com'),'vpn.example.com')
        for x in ['../root','x\ny','x;id','-x','a'*65]:
            with self.assertRaises(ValueError): username(x)
        for x in ['localhost','127.0.0.1','a;id.com','-vpn.example.com']:
            with self.assertRaises(ValueError): hostname(x)
    def test_user_password_block_edit(self):
        self.s.save_user({'name':'Easin','password':'examplePass123','protocols':['openvpn','openconnect','v2ray']})
        self.assertTrue(self.s.verify('Easin','examplePass123'))
        self.s.save_user({'name':'Easin','enabled':False})
        self.assertFalse(self.s.verify('Easin','examplePass123'))
        self.assertNotIn('password_hash',self.s.users()[0])
    def test_counter_reset_duplicate_sessions_durable(self):
        def rows(a,b): return [{'id':'1','user':'Easin','rx':a,'tx':0},{'id':'2','user':'Easin','rx':b,'tx':0}]
        self.s.account('openvpn','boot1',rows(100,200))
        self.s.account('openvpn','boot1',rows(150,220))
        self.assertEqual(self.s.totals()['total'],370)
        self.s.account('openvpn','boot1',rows(150,220))
        self.assertEqual(self.s.totals()['total'],370)
        self.s.account('openvpn','boot2',rows(10,20))
        self.assertEqual(self.s.totals()['total'],400)
        other=State(self.s.path); self.assertEqual(other.totals()['total'],400)
    def test_user_protocol_bounds(self):
        with self.assertRaises(ValueError): self.s.save_user({'name':'Easin','password':'abc123456','protocols':['bad']})
        with self.assertRaises(ValueError): self.s.save_user({'name':'Easin','password':'abc123456','speed_mbps':-1})
    def test_initial_user_required_password(self):
        with self.assertRaises(ValueError): self.s.save_user({'name':'Someone','protocols':['openvpn']})
    def test_password_newline_rejected(self):
        with self.assertRaises(ValueError): hash_password('password\nother')
    def test_restore_user_after_delete(self):
        old=self.s.save_user({'name':'Easin','password':'abc123456'});self.s.delete('Easin');self.s.put_raw(old)
        self.assertTrue(self.s.verify('Easin','abc123456'))
    def test_new_timezone_future_bucket(self):
        self.s.set_setting('timezone','Asia/Dhaka');self.s.account('openvpn','b',[{'id':'1','user':'Easin','rx':100,'tx':0}],now=1767220200)
        self.assertEqual(self.s.totals()['history'][0]['day'],'2026-01-01')
