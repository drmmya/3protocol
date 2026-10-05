"""Root control boundary: fixed JSON commands over a private Unix socket."""
import copy,grp,json,os,socketserver,threading,time,traceback
from pathlib import Path
from zoneinfo import ZoneInfo
from .common import load_config,PROTOCOLS,run,username
from .state import State
from .protocols import Protocols,UNITS
from .metrics import Metrics
from .policies import Shaper
from .domains import issue

class Agent:
    def __init__(self,config,system=True):
        self.config=config;self.state=State(config['state']);self.protocols=Protocols(self.state,config);self.metrics=Metrics(config.get('interface','eth0'));self.shaper=Shaper();self.lock=threading.RLock();self.jobs={};self.snapshot={'ready':False,'sampled_at':None};self.system=system;self.policy_allowed={};self.last_sessions=set()
    def public_jobs(self):
        return [{k:v for k,v in x.items() if k!='thread'} for x in list(self.jobs.values())[-20:]][::-1]
    def job(self,label,fn):
        import secrets
        jid=secrets.token_hex(8);data={'id':jid,'label':label,'status':'running','at':time.time(),'error':None};self.jobs[jid]=data
        def work():
            try:
                with self.lock: data['result']=fn()
                data['status']='completed';self.state.event('job',label+' completed')
            except Exception as e: data['error']=str(e);data['status']='failed';self.state.event('error',label+': '+str(e))
        t=threading.Thread(target=work,daemon=True);data['thread']=t;t.start();return jid
    def collect_once(self):
        with self.lock:
            protocols=self.protocols.snapshot();users={u['name']:u for u in self.state.raw_users()};changed=False;active=set();pending_policies={}
            for p,info in protocols.items():
                if info.get('read_failed'): active.update(identity for identity in self.last_sessions if identity[0]==p)
                for s in info['sessions']:
                    identity=(p,s['id']);active.add(identity)
                    if p!='v2ray' and not s.get('sample_stale') and identity not in self.last_sessions: self.state.event('connect',f"{p}: {s['user']} session {s['id']}")
                    if not s.get('sample_stale') and not self.state.allowed(users.get(s['user']),p):
                        if p!='v2ray':
                            try: self.protocols.disconnect(p,s['id'])
                            except Exception as e: info['errors'].append('Policy disconnect: '+str(e))
                for u in users.values():
                    key=(p,u['name']);allowed=self.state.allowed(u,p)
                    if (self.policy_allowed.get(key,allowed)!=allowed or key not in self.policy_allowed and u['quota_gb']) and p in ('openconnect','v2ray'): changed=True
                    pending_policies[key]=allowed
            for p,sid in self.last_sessions-active:
                if p!='v2ray': self.state.event('disconnect',f'{p}: session {sid}')
            self.last_sessions=active
            if not protocols['openvpn'].get('read_failed'): self.shaper.apply(protocols['openvpn']['sessions'],users,self.state.setting('session_speed',{}))
            if changed:
                self.protocols.sync_users();run(['systemctl','reload','ocserv'],check=False)
            self.policy_allowed=pending_policies
            self.snapshot={'ready':True,'sampled_at':time.time(),'health':self.metrics.read(),'protocols':protocols,'traffic':self.state.totals(),'domain':self.state.setting('domain'),'endpoint':self.state.setting('endpoint',self.config['endpoint']),'xray_tls':self.state.setting('xray_tls',False)}
    def collect_loop(self):
        while True:
            try: self.collect_once()
            except Exception as e:
                self.snapshot={**self.snapshot,'collector_error':str(e),'ready':False}
                print('Collector error:',str(e),flush=True)
            time.sleep(2)
    def save_user(self,data):
        old=self.state.get(username(data.get('name')))
        merged={**(old or {}),**data}
        if float(merged.get('speed_mbps',0)) and 'v2ray' in merged.get('protocols',PROTOCOLS): raise ValueError('Xray per-user speed shaping is not implemented; set speed on OpenVPN/OpenConnect-only users or use OpenVPN session controls.')
        name=username(data.get('name'));old=self.state.get(name)
        try:
            u=self.state.save_user(data)
            if data.get('password'):
                u['oc_hash']=self.protocols.make_oc_hash(name,data['password']);self.state.put_raw(u)
            self.protocols.snapshot() # Flush counters before engine restart.
            self.protocols.sync_users();run(['systemctl','reload','ocserv'],check=False)
            self.disconnect_user(name)
            self.state.event('user',name+' created/updated; sessions disconnected to apply policies')
        except Exception:
            if old: self.state.put_raw(old)
            else: self.state.delete(name)
            try: self.protocols.sync_users()
            except Exception: pass
            raise
        return {'saved':name}
    def disconnect_user(self,name):
        for p in ('openvpn','openconnect'):
            for s in self.snapshot.get('protocols',{}).get(p,{}).get('sessions',[]):
                if s['user']==name: self.protocols.disconnect(p,s['id'])
    def dispatch(self,req):
        action=req.get('action')
        if action=='snapshot': return {**copy.deepcopy(self.snapshot),'jobs':self.public_jobs()}
        if action=='users': return self.state.users()
        if action=='events': return self.state.events()
        if action=='jobs': return self.public_jobs()
        if action=='export': return {'content':self.protocols.export(req.get('protocol'),username(req.get('name')),req.get('transport','tcp'),req.get('format','link'))}
        if action=='logs':
            p=req.get('protocol')
            if p not in UNITS: raise ValueError('Invalid protocol.')
            args=['journalctl','--no-pager','-n','250','-o','short-iso']
            for unit in UNITS[p]: args.extend(['-u',unit])
            if p=='v2ray':
                log=Path('/var/log/vpn-panel/xray-access.log')
                return {'content':run(args)+'\n'+(''.join(run(['tail','-c','262144',str(log)]).splitlines(keepends=True)[-250:]) if log.exists() else '')}
            return {'content':run(args)}
        if action=='save_user': return {'job':self.job('Save user',lambda:self.save_user(req.get('user',{})))}
        if action=='delete_user':
            name=username(req.get('name'))
            def delete():
                old=self.state.get(name)
                if not old: raise ValueError('User not found.')
                self.protocols.snapshot();self.state.delete(name)
                try: self.protocols.sync_users();self.disconnect_user(name)
                except Exception: self.state.put_raw(old);self.protocols.sync_users();raise
                self.state.event('user','Deleted '+name)
            return {'job':self.job('Delete '+name,delete)}
        if action=='service':
            p=req.get('protocol');op=req.get('operation')
            if p not in PROTOCOLS or op not in ('start','stop','restart'): raise ValueError('Invalid service action.')
            def control():
                self.protocols.snapshot();self.protocols.service(p,op)
            return {'job':self.job(op+' '+p,control)}
        if action=='disconnect':
            p=req.get('protocol');sid=req.get('id')
            if p not in ('openvpn','openconnect') or not isinstance(sid,str) or len(sid)>120: raise ValueError('Invalid session.')
            with self.lock: self.protocols.disconnect(p,sid);self.state.event('disconnect',p+' '+sid+' by administrator')
            return {'ok':True}
        if action=='session_speed':
            sid=req.get('id');rate=float(req.get('speed_mbps',0))
            if not 0<=rate<=100000 or not isinstance(sid,str): raise ValueError('Invalid speed.')
            if sid not in [s['id'] for s in self.snapshot.get('protocols',{}).get('openvpn',{}).get('sessions',[])]: raise ValueError('Active OpenVPN session not found.')
            with self.lock:
                overrides=self.state.setting('session_speed',{});overrides[sid]=rate;self.state.set_setting('session_speed',overrides)
            return {'ok':True,'note':'Applies to this active session; user policy controls reconnects.'}
        if action=='domain':
            from .common import hostname
            host=hostname(req.get('hostname'));email=req.get('email')
            return {'job':self.job('Install SSL for '+host,lambda:issue(self,host,email))}
        if action=='settings':
            tz=req.get('timezone','Asia/Dhaka')
            try: ZoneInfo(tz)
            except Exception: raise ValueError('Invalid timezone.')
            self.state.set_setting('timezone',tz);return {'ok':True}
        raise ValueError('Unknown agent command.')

class SocketHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(10)
        try:
            raw=self.rfile.readline(65537)
            if len(raw)>65536 or not raw.endswith(b'\n'): raise ValueError('Request too large.')
            req=json.loads(raw)
            if not isinstance(req,dict): raise ValueError('Object required.')
            result={'ok':True,'data':self.server.agent.dispatch(req)}
        except Exception as e: result={'ok':False,'error':str(e)}
        self.wfile.write((json.dumps(result)+'\n').encode())
class UnixServer(socketserver.ThreadingUnixStreamServer): daemon_threads=True

def main():
    os.umask(0o077);cfg=load_config();agent=Agent(cfg);path=Path(cfg['socket']);path.parent.mkdir(parents=True,exist_ok=True);path.unlink(missing_ok=True)
    with UnixServer(str(path),SocketHandler) as server:
        server.agent=agent;os.chown(path,0,grp.getgrnam('vpn-panel').gr_gid);os.chmod(path,0o660)
        threading.Thread(target=agent.collect_loop,daemon=True).start();server.serve_forever()
if __name__=='__main__': main()
