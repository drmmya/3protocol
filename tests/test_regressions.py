import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from panel.agent import Agent
from panel.policies import Shaper
class RegressionTests(unittest.TestCase):
    def test_openvpn_vendor_config_directory_preserved(self):
        source=(Path(__file__).parents[1]/'scripts/provision.py').read_text()
        self.assertNotIn('WorkingDirectory=/opt/vpn-panel\\nProtectSystem=false\\nReadWritePaths',source)
    def test_quota_sync_retries_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Agent({'state':str(Path(tmp)/'db'),'endpoint':'203.0.113.1'},system=False)
            a.state.save_user({'name':'Easin','password':'TestPassword123','quota_gb':1})
            rows={'openvpn':{'sessions':[],'errors':[]},'openconnect':{'sessions':[],'errors':[]},'v2ray':{'sessions':[],'errors':[]}}
            attempts=[]
            def sync():
                attempts.append(1)
                if len(attempts)==1:raise RuntimeError('transient apply failure')
            with patch.object(a.protocols,'snapshot',return_value=rows),patch.object(a.protocols,'sync_users',side_effect=sync),patch.object(a.shaper,'apply'),patch('panel.agent.run',return_value=''):
                with self.assertRaises(RuntimeError):a.collect_once()
                a.collect_once()
            self.assertEqual(len(attempts),2)
    def test_shaper_reapplies_after_engine_restart(self):
        shape=Shaper();sessions=[{'id':'s1','listener':'panel-udp','virtual_ip':'10.70.0.2','user':'Easin','epoch':'boot1'}];users={'Easin':{'speed_mbps':1}}
        with patch('panel.policies.run',return_value='') as cmd:
            shape.apply(sessions,users,{});first=cmd.call_count
            shape.apply(sessions,users,{});self.assertEqual(cmd.call_count,first)
            sessions[0]['epoch']='boot2';shape.apply(sessions,users,{})
            self.assertGreater(cmd.call_count,first)
    def test_provision_never_seeds_protocol_accounts(self):
        import scripts.provision as provision
        import inspect
        source=inspect.getsource(provision)
        self.assertNotIn('seed_user',source)
        self.assertNotIn('VPN_TEST_PASSWORD',source)
        with tempfile.TemporaryDirectory() as tmp:
            from panel.state import State
            state=State(Path(tmp)/'db')
            self.assertIsNone(state.get('Easin'))
    def test_installer_only_requests_admin_password(self):
        source=(Path(__file__).resolve().parents[1]/'install.sh').read_text()
        self.assertNotIn('VPN_TEST_PASSWORD',source)
        self.assertEqual(source.count('read -r -s -p'),1)
    def test_openvpn_incomplete_sample_is_not_empty_healthy(self):
        from panel.protocols import parse_openvpn
        for raw in ['', 'HEADER\tCLIENT_LIST\tCommon Name\n']:
            with self.assertRaises(ValueError):parse_openvpn(raw,'panel-udp')
    def test_ocserv_reused_id_counts_new_session(self):
        from panel.protocols import parse_ocserv
        from panel.state import State
        with tempfile.TemporaryDirectory() as tmp:
            s=State(Path(tmp)/'db')
            for started,value in [(100,100),(200,150)]:
                rows=parse_ocserv([{'ID':12,'Username':'Easin','raw_connected_at':started,'RX':value,'TX':0}]);s.account('openconnect','boot',rows)
            self.assertEqual(s.totals()['total'],250)
    def test_unknown_occtl_format_rejected(self):
        from panel.protocols import parse_ocserv
        with self.assertRaises(ValueError):parse_ocserv({'unexpected':'data'})
    def test_failed_validation_does_not_restart_engine(self):
        from panel.protocols import Protocols
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'xray.json';path.write_text('{"old":true}')
            p=Protocols(None,{});p.xray_path=path
            with patch('panel.protocols.run',side_effect=RuntimeError('invalid config')) as cmd:
                with self.assertRaises(RuntimeError):p.apply_xray({'bad':True})
                self.assertFalse(any(c.args[0][0]=='systemctl' for c in cmd.call_args_list))
            self.assertEqual(path.read_text(),'{"old":true}')
    def test_failed_collection_preserves_session_audit_and_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Agent({'state':str(Path(tmp)/'db'),'endpoint':'203.0.113.1'},system=False)
            a.last_sessions={('openvpn','old-session')}
            rows={p:{'sessions':[],'errors':['read failed'] if p=='openvpn' else [],'read_failed':p=='openvpn'} for p in ('openvpn','openconnect','v2ray')}
            with patch.object(a.protocols,'snapshot',return_value=rows),patch.object(a.shaper,'apply') as shape:
                a.collect_once()
                shape.assert_not_called()
            self.assertIn(('openvpn','old-session'),a.last_sessions)
            self.assertFalse(any(e['kind']=='disconnect' for e in a.state.events()))
    def test_log_read_uses_bounded_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Agent({'state':str(Path(tmp)/'db'),'endpoint':'203.0.113.1'},system=False)
            with patch('panel.agent.run',return_value='logs') as cmd,patch('panel.agent.Path') as paths:
                paths.return_value.exists.return_value=True
                a.dispatch({'action':'logs','protocol':'v2ray'})
                self.assertTrue(any(c.args[0][:3]==['tail','-c','262144'] for c in cmd.call_args_list))
    def test_openvpn_missing_counter_columns_rejected(self):
        from panel.protocols import parse_openvpn
        with self.assertRaises(ValueError):parse_openvpn('HEADER\tCLIENT_LIST\tCommon Name\nCLIENT_LIST\tEasin\nEND\n','panel-udp')
    def test_ocserv_invalid_user_row_rejected(self):
        from panel.protocols import parse_ocserv
        with self.assertRaises(ValueError):parse_ocserv([{'unexpected':123}])
