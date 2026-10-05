import unittest
from panel.protocols import parse_openvpn, parse_ocserv, parse_xray_stats, vmess_link
import base64,json
class ProtocolTests(unittest.TestCase):
    def test_openvpn_duplicate_name(self):
        raw='HEADER\tCLIENT_LIST\tCommon Name\tReal Address\tVirtual Address\tVirtual IPv6 Address\tBytes Received\tBytes Sent\tConnected Since\tConnected Since (time_t)\tUsername\tClient ID\tPeer ID\tData Channel Cipher\nCLIENT_LIST\tEasin\t1.2.3.4:9000\t10.70.0.2\t\t100\t200\tnow\t123\tEasin\t0\t1\tAES\nCLIENT_LIST\tEasin\t1.2.3.5:9000\t10.70.0.3\t\t150\t300\tnow\t124\tEasin\t1\t2\tAES\nEND\n'
        s=parse_openvpn(raw,'openvpn-udp'); self.assertEqual(len(s),2); self.assertEqual(s[0]['rx'],100)
        self.assertNotEqual(s[0]['id'],s[1]['id']); self.assertEqual(s[1]['user'],'Easin')
    def test_ocserv_json(self):
        rows=parse_ocserv({'users':[{'id':12,'username':'Easin','remote-ip':'1.2.3.4','vpn-ipv4':'10.72.0.2','RX':100,'TX':200}]})
        self.assertEqual(rows[0]['id'],'12'); self.assertEqual(rows[0]['tx'],200)
    def test_xray_stats(self):
        s=parse_xray_stats({'stat':[{'name':'user>>>Easin>>>traffic>>>uplink','value':100},{'name':'user>>>Easin>>>traffic>>>downlink','value':230}]})
        self.assertEqual(s['Easin'],{'rx':100,'tx':230})
    def test_vmess_export(self):
        link=vmess_link('vpn.example.com',4443,'uuid','Easin',True)
        p=json.loads(base64.b64decode(link.split('://')[1])); self.assertEqual(p['tls'],'tls');self.assertEqual(p['port'],'4443')
    def test_ocserv_machine_fields(self):
        x=parse_ocserv([{'ID':12,'Username':'Easin','Device':'vpnc0','Remote IP':'1.2.3.4','IPv4':'10.72.0.2','RX':'100','TX':'200','raw_connected_at':123}])[0]
        self.assertEqual(x['since'],123);self.assertEqual(x['device'],'vpnc0');self.assertTrue(x['has_counters'])
    def test_online_value(self):
        from panel.protocols import parse_online
        self.assertEqual(parse_online({'stat':{'name':'user>>>Easin>>>online','value':'2'}}),2)
        with self.assertRaises(ValueError):parse_online({'unexpected':1})
    def test_vmess_udp_export(self):
        link=vmess_link('vpn.example.com',4443,'uuid','Easin',False,'kcp')
        p=json.loads(base64.b64decode(link.split('://')[1]));self.assertEqual(p['net'],'kcp');self.assertEqual(p['tls'],'')
    def test_complete_udp_client_profile_matches_legacy_mask(self):
        from panel.protocols import client_json
        cfg=client_json('vpn.example.com',4443,'uuid',False,'kcp')
        self.assertEqual(cfg['outbounds'][0]['streamSettings']['finalmask']['udp'][0]['type'],'mkcp-legacy')
        self.assertTrue(cfg['inbounds'][0]['settings']['udp'])
