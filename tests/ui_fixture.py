"""HTTPS UI test fixture. This does not emulate VPN routing or an installer."""
import json,ssl,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from panel.web import Auth,WebServer
from panel.common import run
from panel.metrics import Metrics
folder=Path(tempfile.mkdtemp(prefix='vpn-ui-test-'));auth=Auth(folder/'admin.db');auth.bootstrap('Admin','TestOnlyPassword123')
run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-keyout',str(folder/'key.pem'),'-out',str(folder/'cert.pem')])
users=[{'name':'Easin','enabled':True,'protocols':['openvpn','openconnect','v2ray'],'speed_mbps':0,'quota_gb':0,'quota_period':'daily'}]
metrics=Metrics('lo')
def rpc(r):
    if r['action']=='users':return users
    if r['action']=='events':return [{'at':time.time(),'kind':'UI TEST FIXTURE','message':'Synthetic protocol data for browser verification; not a VPN routing test.'}]
    if r['action']=='snapshot':
        pro={p:{'status':'active','count':n,'sessions':[],'online':None,'errors':[],'rx_rate':0,'tx_rate':0} for p,n in [('openvpn',2),('openconnect',1),('v2ray',None)]}
        return {'ready':True,'sampled_at':time.time(),'health':metrics.read(),'protocols':pro,'traffic':{'today':12345678,'total':56789012,'history':[{'day':'2026-10-05','rx':1234,'tx':2345}],'users':[],'timezone':'Asia/Dhaka','accounting':'UI TEST FIXTURE: synthetic traffic, not VPN routing evidence.'},'endpoint':'UI TEST FIXTURE','domain':None,'jobs':[]}
    if r['action']=='save_user':
        (folder/'last-mutation.json').write_text(json.dumps(r));return {'job':'test-job'}
    if r['action']=='export':return {'content':'UI TEST FIXTURE CONNECTION PROFILE'}
    if r['action']=='logs':return {'content':'UI TEST FIXTURE LOGS'}
    return {'ok':True}
server=WebServer(('127.0.0.1',19443),auth,rpc);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(folder/'cert.pem',folder/'key.pem');server.socket=ctx.wrap_socket(server.socket,server_side=True)
print('UI fixture ready on https://127.0.0.1:19443',flush=True);server.serve_forever()
