"""Engine adapters. Source values retain session/online-IP semantics."""
import base64, ipaddress, json, socket, time
from pathlib import Path
from .common import run,atomic_write,PROTOCOLS,endpoint
UNITS={'openvpn':['openvpn-server@panel-udp','openvpn-server@panel-tcp'],'openconnect':['ocserv'],'v2ray':['vpn-panel-xray']}

def parse_openvpn(raw,listener):
    if 'END' not in raw.splitlines() or not any(line.startswith('HEADER\tCLIENT_LIST\t') for line in raw.splitlines()): raise ValueError('Incomplete OpenVPN status response.')
    header=[];rows=[]
    for line in raw.splitlines():
        cells=line.split('\t')
        if cells[:2]==['HEADER','CLIENT_LIST']:
            header=cells[2:]
            required={'Common Name','Real Address','Virtual Address','Bytes Received','Bytes Sent','Connected Since (time_t)','Client ID'}
            if not required.issubset(header): raise ValueError('OpenVPN status columns are missing.')
        elif cells[0]=='CLIENT_LIST' and header:
            if len(cells)-1<len(header): raise ValueError('Truncated OpenVPN session row.')
            x=dict(zip(header,cells[1:]));cid=x.get('Client ID','');start=x.get('Connected Since (time_t)','')
            rows.append({'id':f'{listener}:{cid}:{start}','control_id':cid,'listener':listener,'user':x.get('Username') or x.get('Common Name'),'public_ip':x.get('Real Address'),'virtual_ip':x.get('Virtual Address'),'rx':int(x.get('Bytes Received',0)),'tx':int(x.get('Bytes Sent',0)),'since':start,'kind':'VPN session'})
    return rows

def parse_ocserv(data):
    if isinstance(data,list): users=data
    elif isinstance(data,dict) and ('users' in data or 'Users' in data): users=data.get('users',data.get('Users'))
    else: raise ValueError('Unknown occtl users format')
    if isinstance(users,dict): users=list(users.values())
    out=[]
    for x in users:
        y={str(k).lower():v for k,v in x.items()}
        def get(*keys,default=''):
            return next((y[k] for k in keys if k in y),default)
        if not str(get('id','session id')).isdigit() or not get('username','user'): raise ValueError('Unknown occtl session row format.')
        out.append({'id':str(get('id','session id'))+((':'+str(get('raw_connected_at','connected at','connected-at'))) if get('raw_connected_at','connected at','connected-at')!='' else ''),'control_id':str(get('id','session id')),'user':get('username','user'),'public_ip':get('remote-ip','remote ip','ip'),'virtual_ip':get('vpn-ipv4','vpn ipv4','ipv4'),'rx':int(get('raw_rx','rx','rx bytes',default=0)),'tx':int(get('raw_tx','tx','tx bytes',default=0)),'since':get('raw_connected_at','connected at','connected-at'),'device':get('device'),'has_counters':any(k in y for k in ('rx','raw_rx','rx bytes')) and any(k in y for k in ('tx','raw_tx','tx bytes')),'kind':'VPN session'})
    return out

def parse_xray_stats(data):
    result={}
    for s in data.get('stat',[]):
        parts=s['name'].split('>>>')
        if len(parts)==4 and parts[0]=='user' and parts[2]=='traffic':
            row=result.setdefault(parts[1],{'rx':0,'tx':0});key='rx' if parts[3]=='uplink' else 'tx'
            row[key]=int(s.get('value',0))
    return result

def parse_online(data):
    value=data.get('stat',data)
    if isinstance(value,dict) and 'value' in value: return max(0,int(value['value']))
    raise ValueError('Unknown online statistics format.')

def vmess_link(host,port,uid,name,tls,transport='tcp'):
    if transport not in ('tcp','kcp'): raise ValueError('Unsupported VMess transport.')
    if transport=='kcp': tls=False
    payload={'v':'2','ps':name,'add':host,'port':str(port),'id':uid,'aid':'0','scy':'auto','net':transport,'type':'none','host':'','path':'','tls':'tls' if tls else '','sni':host if tls else ''}
    return 'vmess://'+base64.b64encode(json.dumps(payload,separators=(',',':')).encode()).decode()

def client_json(host,port,uid,tls,transport='tcp'):
    if transport not in ('tcp','kcp'): raise ValueError('Unsupported transport.')
    stream={'network':transport,'security':'tls' if tls and transport=='tcp' else 'none'}
    if transport=='kcp': stream.update({'kcpSettings':{},'finalmask':{'udp':[{'type':'mkcp-legacy','settings':{'header':'','value':''}}]}})
    elif tls: stream['tlsSettings']={'serverName':host}
    return {'inbounds':[{'listen':'127.0.0.1','port':10808,'protocol':'socks','settings':{'udp':True}}], 'outbounds':[{'protocol':'vmess','settings':{'vnext':[{'address':host,'port':port,'users':[{'id':uid,'alterId':0,'security':'auto'}]}]},'streamSettings':stream}]}

def management(path,command):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
        s.settimeout(3);s.connect(str(path));s.recv(8192);s.sendall((command+'\nquit\n').encode());chunks=[]
        while True:
            try: part=s.recv(65536)
            except socket.timeout: break
            if not part: break
            chunks.append(part)
        return b''.join(chunks).decode(errors='replace')

class Protocols:
    def __init__(self,state,config): self.state=state;self.config=config;self.prior={};self.policy_cache={};self.last_good={};self.xray_path=Path('/etc/vpn-panel/xray.json')
    def epoch(self,unit):
        return run(['systemctl','show',unit,'--property=InvocationID','--value']).strip() or 'stopped'
    def snapshot(self):
        result={}
        for p in PROTOCOLS:
            now=time.time(); sessions=[]; errors=[]; epochs=[];states=[]; online=None;read_failed=False
            for unit in UNITS[p]:
                state=run(['systemctl','is-active',unit],check=False).strip();states.append(state)
                if state!='active': errors.append(f'{unit}: {state}');continue
                try:
                    ep=self.epoch(unit);epochs.append(ep)
                    if p=='openvpn':
                        listener=unit.split('@')[1];rows=parse_openvpn(management('/run/vpn-panel/'+listener+'.sock','status 3'),listener)
                    elif p=='openconnect':
                        rows=parse_ocserv(json.loads(run(['occtl','-j','show','users'])))
                        for row in rows:
                            if not row['has_counters']:
                                device=row['device']
                                if not __import__('re').fullmatch(r'vpnc[0-9]+',device): raise ValueError('occtl did not expose traffic counters or a known tunnel device.')
                                stat=Path('/sys/class/net')/device/'statistics'
                                row['rx']=int((stat/'rx_bytes').read_text());row['tx']=int((stat/'tx_bytes').read_text())
                    else:
                        traffic=parse_xray_stats(json.loads(run(['/usr/local/bin/xray','api','statsquery','--server=127.0.0.1:10085','-pattern','user>>>'])))
                        rows=[{'id':name,'user':name,**values,'kind':'User traffic counter','public_ip':'','virtual_ip':''} for name,values in traffic.items()]
                        online={'users':[],'total_online_sources':0,'errors':[]}
                        for user in self.state.users():
                            if 'v2ray' not in user['protocols']: continue
                            try:
                                count=parse_online(json.loads(run(['/usr/local/bin/xray','api','statsonline','--server=127.0.0.1:10085','--email='+user['name']],timeout=3)))
                                online['users'].append({'user':user['name'],'online_sources':count});online['total_online_sources']+=count
                            except Exception as e: online['errors'].append(user['name']+': '+str(e)[:120])
                        if online['errors']: online['total_online_sources']=None
                    self.state.account(p,ep,rows,now)
                    for row in rows:
                        row['epoch']=ep
                        key=(p,ep,row['id']);previous=self.prior.get(key)
                        row['rx_rate']=max(0,(row['rx']-previous[0])/(now-previous[2])) if previous else 0
                        row['tx_rate']=max(0,(row['tx']-previous[1])/(now-previous[2])) if previous else 0
                        self.prior[key]=(row['rx'],row['tx'],now)
                    self.last_good[unit]=rows
                    sessions.extend(rows)
                except Exception as e:
                    read_failed=True;errors.append(f'{unit}: {str(e)[:250]}')
                    sessions.extend([{**row,'sample_stale':True,'rx_rate':None,'tx_rate':None} for row in self.last_good.get(unit,[])])
            result[p]={'status':'active' if all(s=='active' for s in states) and not errors else 'degraded' if 'active' in states else 'stopped','sessions':sessions,'count':len(sessions) if p!='v2ray' and not errors else online.get('total_online_sources') if p=='v2ray' and online and not errors else None,'count_label':'Active VPN sessions' if p!='v2ray' else 'Online user/source observations','online':online,'errors':errors,'read_failed':read_failed,'sampled_at':now,'rx_rate':sum(x.get('rx_rate') or 0 for x in sessions),'tx_rate':sum(x.get('tx_rate') or 0 for x in sessions)}
        return result
    def service(self,p,action):
        if p not in UNITS or action not in ('start','stop','restart'): raise ValueError('Invalid service action.')
        for unit in UNITS[p]: run(['systemctl',action,unit],timeout=45)
    def disconnect(self,p,sid):
        if p=='openvpn':
            listener,cid,_=sid.split(':')
            if listener not in ('panel-udp','panel-tcp') or not cid.isdigit(): raise ValueError('Invalid session.')
            out=management('/run/vpn-panel/'+listener+'.sock','client-kill '+cid)
            if 'ERROR' in out: raise RuntimeError('OpenVPN rejected disconnect.')
        elif p=='openconnect' and str(sid).split(':')[0].isdigit(): run(['occtl','disconnect','id',str(sid).split(':')[0]])
        else: raise ValueError('This engine supports user blocking, not individual proxy-socket disconnect.')
    def make_oc_hash(self,name,password):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'passwd';run(['ocpasswd','-c',str(path),name],input=password+'\n'+password+'\n')
            return path.read_text().strip()
    def sync_users(self):
        oc=[];clients=[]
        for u in self.state.raw_users():
            if self.state.allowed(u,'openconnect'):
                if not u.get('oc_hash'): raise ValueError('OpenConnect password hash missing; reset this user password.')
                oc.append(u['oc_hash'])
            rate=int(u['speed_mbps']*1e6/8)
            atomic_write('/etc/ocserv/panel-users/'+u['name'],f'rx-data-per-sec = {rate}\ntx-data-per-sec = {rate}\n')
            if self.state.allowed(u,'v2ray'): clients.append({'id':u['uuid'],'email':u['name'],'level':0,'alterId':0})
        atomic_write('/etc/ocserv/panel.passwd','\n'.join(oc)+'\n')
        cfg=json.loads(self.xray_path.read_text())
        for inbound in cfg['inbounds']:
            if inbound['protocol']=='vmess': inbound['settings']['clients']=clients
        self.apply_xray(cfg)
    def apply_xray(self,cfg):
        path=self.xray_path;old=path.read_text();candidate=path.with_suffix('.candidate.json');installed=False
        atomic_write(candidate,json.dumps(cfg,indent=2))
        try:
            run(['/usr/local/bin/xray','run','-test','-config',str(candidate)])
            atomic_write(path,candidate.read_text());installed=True;run(['systemctl','restart','vpn-panel-xray'],timeout=45)
            if run(['systemctl','is-active','vpn-panel-xray'],check=False).strip()!='active': raise RuntimeError('Xray health check failed.')
        except Exception:
            if installed:
                atomic_write(path,old);run(['systemctl','restart','vpn-panel-xray'],check=False,timeout=45)
            raise
        finally: candidate.unlink(missing_ok=True)
    def export(self,p,name,transport='tcp',format='link'):
        if format not in ('link','json'): raise ValueError('Invalid export format.')
        u=self.state.get(name)
        if not u or p not in u['protocols']: raise ValueError('User/protocol not found.')
        host=endpoint(self.state.setting('endpoint',self.config['endpoint']));tls=self.state.setting('xray_tls',False)
        if p=='v2ray': return json.dumps(client_json(host,4443,u['uuid'],tls,transport),indent=2) if format=='json' else vmess_link(host,4443,u['uuid'],name,tls,transport)
        if p=='openconnect': return json.dumps({'server':f'https://{host}:8443','username':name,'certificate_note':'Trust the server certificate fingerprint in IP-only mode.'},indent=2)
        if p=='openvpn':
            ca=Path('/etc/vpn-panel/pki/ca.crt').read_text();key=Path('/etc/vpn-panel/pki/tls-crypt.key').read_text()
            return f'client\ndev tun\nremote {host} 1194 udp\nremote {host} 443 tcp-client\nresolv-retry infinite\nnobind\npersist-key\npersist-tun\nremote-cert-tls server\nverify-x509-name vpn-panel name\nauth-user-pass\nauth-nocache\nverb 3\nblock-ipv6\n<ca>\n{ca}</ca>\n<tls-crypt>\n{key}</tls-crypt>\n'
        raise ValueError('Unknown protocol.')
