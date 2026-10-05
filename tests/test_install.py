import json
import unittest,importlib.util
from pathlib import Path
from panel.domains import nginx_config
class InstallTests(unittest.TestCase):
    def load(self):
        spec=importlib.util.spec_from_file_location('provision',Path(__file__).parents[1]/'scripts/provision.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    def test_ports_and_pools(self):
        p=self.load();u=p.openvpn_config('udp');t=p.openvpn_config('tcp');o=p.ocserv_config()
        self.assertIn('port 1194',u);self.assertIn('port 443',t);self.assertIn('tcp-server',t)
        self.assertIn('10.70.0.0',u);self.assertIn('10.71.0.0',t);self.assertIn('8443',o)
        self.assertIn('max-clients = 0',o);self.assertIn('max-same-clients = 0',o)
        self.assertIn('auth-user-pass-verify',u);self.assertIn('duplicate-cn',u)
    def test_local_only_xray_api(self):
        cfg=self.load().xray_config();self.assertEqual(cfg['inbounds'][0]['port'],4443)
        self.assertEqual(cfg['inbounds'][1]['listen'],'127.0.0.1');self.assertIn('stats',cfg)
    def test_nginx_ssl_separate_port(self):
        conf=nginx_config('/cert','/key');self.assertIn('listen 9443 ssl',conf);self.assertNotIn('listen 443',conf)
    def test_firewall_scoped(self):
        source=(Path(__file__).parents[1]/'scripts/firewall.sh').read_text()
        self.assertNotIn('iptables -F\n',source);self.assertIn('VPNP_FORWARD',source)
    def test_native_udp4443_mkcp_listener(self):
        cfg=self.load().xray_config();udp=[x for x in cfg['inbounds'] if x.get('streamSettings',{}).get('network')=='kcp']
        self.assertEqual(len(udp),1);self.assertEqual(udp[0]['port'],4443);self.assertEqual(udp[0]['protocol'],'vmess')
    def test_route_overlap_and_default_route(self):
        p=self.load()
        self.assertEqual(p.network_conflicts([{'dst':'default'},{'dst':'10.0.0.0/8'}]),['10.0.0.0/8'])
        self.assertEqual(p.network_conflicts([{'dst':'default'},{'dst':'192.168.1.0/24'}]),[])
        self.assertIn('255.255.0.0',p.openvpn_config('udp'))
    def test_xray_upgrade_keeps_tcp_tls_and_clients(self):
        p=self.load();cfg=p.xray_config();cfg['inbounds']=cfg['inbounds'][:2];cfg['inbounds'][0]['settings']['clients']=[{'id':'existing-uuid','email':'Easin'}]
        cfg['inbounds'][0]['streamSettings']={'network':'tcp','security':'tls','tlsSettings':{'serverName':'example.com'}}
        old=json.loads(json.dumps(cfg['inbounds'][0]))
        new=p.upgrade_xray(cfg);self.assertEqual(new['inbounds'][0],old);self.assertEqual(new['inbounds'][-1]['settings']['clients'],old['settings']['clients'])
        self.assertEqual(new['inbounds'][-1]['streamSettings']['finalmask']['udp'][0]['type'],'mkcp-legacy')
