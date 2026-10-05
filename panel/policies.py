"""Rate enforcement on panel-owned OpenVPN TUN interfaces only."""
import ipaddress
from .common import run
class Shaper:
    def __init__(self): self.cache={}
    def apply(self,sessions,users,overrides):
        active=set()
        for s in sessions:
            iface={'panel-udp':'vpnu','panel-tcp':'vpnt'}.get(s.get('listener'))
            if not iface: continue
            ip=str(ipaddress.IPv4Address(s['virtual_ip']));key=(iface,ip);active.add(key)
            user=users.get(s['user'],{});rate=float(overrides.get(s['id'],user.get('speed_mbps',0)))
            policy=(rate,s.get('epoch',''))
            if self.cache.get(key)==policy: continue
            n=int(ipaddress.IPv4Address(ip))%65536;pref=str(n);cid=f'1:{n:x}'
            for parent in ('1:','ffff:'): run(['tc','filter','del','dev',iface,'parent',parent,'pref',pref],check=False)
            if rate:
                limit=f'{rate:g}mbit'
                run(['tc','qdisc','add','dev',iface,'root','handle','1:','htb','default','1'],check=False)
                run(['tc','class','replace','dev',iface,'parent','1:','classid','1:1','htb','rate','100gbit'])
                run(['tc','class','replace','dev',iface,'parent','1:','classid',cid,'htb','rate',limit,'ceil',limit])
                run(['tc','filter','add','dev',iface,'parent','1:','protocol','ip','pref',pref,'u32','match','ip','dst',ip+'/32','flowid',cid])
                run(['tc','qdisc','add','dev',iface,'handle','ffff:','ingress'],check=False)
                run(['tc','filter','add','dev',iface,'parent','ffff:','protocol','ip','pref',pref,'u32','match','ip','src',ip+'/32','police','rate',limit,'burst','64k','drop','flowid',':1'])
            else: run(['tc','class','del','dev',iface,'classid',cid],check=False)
            self.cache[key]=policy
        for key in list(self.cache):
            if key not in active:
                iface,ip=key;n=int(ipaddress.IPv4Address(ip))%65536
                for parent in ('1:','ffff:'): run(['tc','filter','del','dev',iface,'parent',parent,'pref',str(n)],check=False)
                run(['tc','class','del','dev',iface,'classid',f'1:{n:x}'],check=False);del self.cache[key]
