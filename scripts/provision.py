#!/usr/bin/env python3
"""Generate managed configuration; repeated installs preserve existing files."""
import argparse,json,os,sys,ipaddress
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from panel.common import atomic_write,run,hash_password,endpoint
from panel.domains import nginx_config
from panel.state import State
from panel.web import Auth
from panel.protocols import Protocols

def network_conflicts(routes):
    pools=[ipaddress.ip_network(f'10.{i}.0.0/16') for i in (70,71,72)]
    conflicts=[]
    for route in routes:
        dst=route.get('dst','default')
        if dst=='default': continue
        try: net=ipaddress.ip_network(dst,strict=False)
        except ValueError: continue
        if net.version==4 and any(net.overlaps(pool) for pool in pools): conflicts.append(dst)
    return conflicts

def openvpn_config(transport):
    tcp=transport=='tcp';pool='10.71.0.0' if tcp else '10.70.0.0';iface='vpnt' if tcp else 'vpnu';port=443 if tcp else 1194;proto='tcp-server' if tcp else 'udp';tag='panel-'+transport;v6='fd70:71::/64' if tcp else 'fd70:70::/64'
    return f'''port {port}
proto {proto}
dev {iface}
dev-type tun
topology subnet
server {pool} 255.255.0.0
server-ipv6 {v6}
push "redirect-gateway def1 ipv6"
block-ipv6
push "block-ipv6"
push "dhcp-option DNS 1.1.1.1"
push "dhcp-option DNS 8.8.8.8"
ca /etc/vpn-panel/pki/ca.crt
cert /etc/vpn-panel/pki/server.crt
key /etc/vpn-panel/pki/server.key
dh none
ecdh-curve prime256v1
tls-crypt /etc/vpn-panel/pki/tls-crypt.key
tls-version-min 1.2
data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305
auth SHA256
verify-client-cert none
username-as-common-name
duplicate-cn
script-security 2
auth-user-pass-verify /opt/vpn-panel/scripts/openvpn-auth.sh via-file
management /run/vpn-panel/{tag}.sock unix
keepalive 10 120
persist-key
persist-tun
explicit-exit-notify {0 if tcp else 1}
verb 3
'''

def ocserv_config():
    return '''auth = "plain[passwd=/etc/ocserv/panel.passwd]"
tcp-port = 8443
udp-port = 8443
run-as-user = nobody
run-as-group = nogroup
socket-file = /run/ocserv.socket
occtl-socket-file = /run/occtl.socket
pid-file = /run/ocserv.pid
server-cert = /etc/vpn-panel/pki/panel.crt
server-key = /etc/vpn-panel/pki/panel.key
isolate-workers = true
max-clients = 0
max-same-clients = 0
keepalive = 30
dpd = 60
mobile-dpd = 180
try-mtu-discovery = true
compression = false
ipv4-network = 10.72.0.0
ipv4-netmask = 255.255.0.0
device = vpnc
predictable-ips = false
dns = 1.1.1.1
dns = 8.8.8.8
route = default
config-per-user = /etc/ocserv/panel-users/
cookie-timeout = 86400
use-occtl = true
log-level = 1
'''

def xray_config():
    return {'log':{'access':'/var/log/vpn-panel/xray-access.log','error':'/var/log/vpn-panel/xray-error.log','loglevel':'warning'},'stats':{},'api':{'tag':'api','services':['StatsService','HandlerService']},'policy':{'levels':{'0':{'statsUserUplink':True,'statsUserDownlink':True,'statsUserOnline':True}}},'inbounds':[{'tag':'vpn','listen':'0.0.0.0','port':4443,'protocol':'vmess','settings':{'clients':[]},'streamSettings':{'network':'tcp','security':'none'}},{'tag':'api-in','listen':'127.0.0.1','port':10085,'protocol':'dokodemo-door','settings':{'address':'127.0.0.1'}},{'tag':'vpn-kcp','listen':'0.0.0.0','port':4443,'protocol':'vmess','settings':{'clients':[]},'streamSettings':{'network':'kcp','security':'none','kcpSettings':{},'finalmask':{'udp':[{'type':'mkcp-legacy','settings':{'header':'','value':''}}]}}}],'outbounds':[{'tag':'direct','protocol':'freedom'},{'tag':'blocked','protocol':'blackhole'}],'routing':{'rules':[{'type':'field','inboundTag':['api-in'],'outboundTag':'api'},{'type':'field','ip':['geoip:private'],'outboundTag':'blocked'}]}}

def upgrade_xray(cfg):
    import copy
    cfg=copy.deepcopy(cfg)
    if not any(i.get('tag')=='vpn-kcp' for i in cfg['inbounds']):
        udp=xray_config()['inbounds'][-1]
        udp['settings']['clients']=copy.deepcopy(cfg['inbounds'][0]['settings']['clients'])
        cfg['inbounds'].append(udp)
    return cfg

def preserve(path,text,mode=0o600):
    if not Path(path).exists(): atomic_write(path,text,mode)

def pki(host):
    folder=Path('/etc/vpn-panel/pki');folder.mkdir(parents=True,exist_ok=True);os.chmod(folder,0o700)
    if not (folder/'ca.crt').exists():
        run(['openssl','req','-x509','-newkey','rsa:3072','-nodes','-days','3650','-subj','/CN=Easin VPN CA','-keyout',str(folder/'ca.key'),'-out',str(folder/'ca.crt')],timeout=90)
    if not (folder/'server.crt').exists():
        run(['openssl','req','-new','-newkey','rsa:3072','-nodes','-subj','/CN=vpn-panel','-keyout',str(folder/'server.key'),'-out',str(folder/'server.csr')],timeout=90)
        atomic_write(folder/'server.ext','basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:vpn-panel\n')
        run(['openssl','x509','-req','-in',str(folder/'server.csr'),'-CA',str(folder/'ca.crt'),'-CAkey',str(folder/'ca.key'),'-CAcreateserial','-days','1825','-extfile',str(folder/'server.ext'),'-out',str(folder/'server.crt')])
    if not (folder/'panel.crt').exists():
        try: ipaddress.ip_address(host);san='IP:'+host
        except ValueError:san='DNS:'+host
        run(['openssl','req','-x509','-newkey','rsa:3072','-nodes','-days','825','-subj','/CN='+host,'-addext','subjectAltName='+san,'-keyout',str(folder/'panel.key'),'-out',str(folder/'panel.crt')],timeout=90)
    if not (folder/'tls-crypt.key').exists():run(['openvpn','--genkey','secret',str(folder/'tls-crypt.key')])
    for file in folder.iterdir():os.chmod(file,0o600)

def unit(command,user='root',extra=''):
    return f'''[Unit]
Description=Easin VPN Panel
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User={user}
Group=vpn-panel
WorkingDirectory=/opt/vpn-panel
ExecStart={command}
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
{extra}
[Install]
WantedBy=multi-user.target
'''

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--endpoint',required=True);parser.add_argument('--interface',required=True);args=parser.parse_args();host=endpoint(args.endpoint)
    os.umask(0o077)
    for directory in ('/etc/vpn-panel','/etc/ocserv/panel-users','/etc/openvpn/server','/var/lib/vpn-panel','/var/lib/vpn-panel/acme','/var/lib/vpn-panel-web','/var/log/vpn-panel'):
        Path(directory).mkdir(parents=True,exist_ok=True)
    preserve('/etc/vpn-panel/config.json',json.dumps({'endpoint':host,'interface':args.interface,'state':'/var/lib/vpn-panel/state.db','socket':'/run/vpn-panel/agent.sock'},indent=2),0o640)
    cfg=json.loads(Path('/etc/vpn-panel/config.json').read_text());pki(cfg['endpoint'])
    for proto in ('udp','tcp'):preserve('/etc/openvpn/server/panel-'+proto+'.conf',openvpn_config(proto))
    preserve('/etc/ocserv/ocserv.conf',ocserv_config());preserve('/etc/vpn-panel/xray.json',json.dumps(xray_config(),indent=2));preserve('/etc/nginx/conf.d/vpn-panel.conf',nginx_config('/etc/vpn-panel/pki/panel.crt','/etc/vpn-panel/pki/panel.key'),0o644)
    xray_path=Path('/etc/vpn-panel/xray.json');current=json.loads(xray_path.read_text());upgraded=upgrade_xray(current)
    if upgraded!=current:
        candidate=xray_path.with_suffix('.upgrade.json');atomic_write(candidate,json.dumps(upgraded,indent=2))
        try:
            run(['/usr/local/bin/xray','run','-test','-config',str(candidate)])
            atomic_write(xray_path,candidate.read_text())
        finally: candidate.unlink(missing_ok=True)
    state=State(cfg['state']);auth=Auth('/var/lib/vpn-panel-web/admin.db')
    with auth.db() as d:has_admin=bool(d.execute('SELECT 1 FROM admin').fetchone())
    if not has_admin:
        password=os.environ.get('PANEL_ADMIN_PASSWORD')
        if not password:raise ValueError('PANEL_ADMIN_PASSWORD required for initial installation.')
        auth.bootstrap('Admin',password)
    preserve('/etc/sysctl.d/90-vpn-panel.conf','net.ipv4.ip_forward=1\nnet.ipv6.conf.all.forwarding=1\n',0o644)
    # Agent needs explicitly scoped filesystem writes and systemd access.
    atomic_write('/etc/systemd/system/vpn-panel-agent.service',unit('/usr/bin/python3 -m panel.agent',extra='Environment=XRAY_LOCATION_ASSET=/usr/local/share/xray\nRuntimeDirectory=vpn-panel\nRuntimeDirectoryMode=0750\nRuntimeDirectoryPreserve=yes\nProtectSystem=false'),0o644)
    atomic_write('/etc/systemd/system/vpn-panel-web.service',unit('/usr/bin/python3 -m panel.web','vpn-panel',extra='ProtectSystem=strict\nReadWritePaths=/var/lib/vpn-panel-web\nRestrictAddressFamilies=AF_INET AF_UNIX\nCapabilityBoundingSet='),0o644)
    atomic_write('/etc/systemd/system/vpn-panel-xray.service',unit('/usr/local/bin/xray run -config /etc/vpn-panel/xray.json',extra='CapabilityBoundingSet=\nEnvironment=XRAY_LOCATION_ASSET=/usr/local/share/xray\nRestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX'),0o644)
    for proto in ('udp','tcp'):
        folder=Path('/etc/systemd/system/openvpn-server@panel-'+proto+'.service.d');folder.mkdir(parents=True,exist_ok=True)
        atomic_write(folder/'panel.conf','[Unit]\nAfter=vpn-panel-agent.service vpn-panel-firewall.service\nRequires=vpn-panel-firewall.service\n[Service]\nProtectSystem=false\nReadWritePaths=/var/lib/vpn-panel\n',0o644)
    atomic_write('/etc/systemd/system/vpn-panel-firewall.service','''[Unit]
Description=Easin VPN scoped forwarding rules
After=network-online.target
Before=openvpn-server@panel-udp.service openvpn-server@panel-tcp.service ocserv.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/vpn-panel/scripts/firewall.sh start
ExecStop=/opt/vpn-panel/scripts/firewall.sh stop
[Install]
WantedBy=multi-user.target
''',0o644)
    preserve('/etc/logrotate.d/vpn-panel','/var/log/vpn-panel/*.log {\n daily\n maxsize 50M\n rotate 14\n compress\n missingok\n notifempty\n copytruncate\n}\n',0o644)
    atomic_write('/etc/letsencrypt/renewal-hooks/deploy/vpn-panel.sh','#!/bin/sh\n/usr/sbin/nginx -t && /usr/bin/systemctl reload nginx\n/usr/bin/systemctl restart ocserv vpn-panel-xray\n',0o755)
    state.event('install','Installation/provisioning completed; credentials preserved on reruns')
if __name__=='__main__':main()
