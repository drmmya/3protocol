"""Optional trusted domain certificates, keeping OpenVPN on 443."""
import ipaddress,json,socket
from pathlib import Path
from .common import hostname,endpoint,run,atomic_write

def nginx_config(cert,key,host='_'):
    return f'''server {{
    listen 80;
    server_name {host};
    location ^~ /.well-known/acme-challenge/ {{ root /var/lib/vpn-panel/acme; }}
    location / {{ return 301 https://$host:9443$request_uri; }}
}}
server {{
    listen 9443 ssl;
    server_name {host};
    ssl_certificate {cert};
    ssl_certificate_key {key};
    ssl_protocols TLSv1.2 TLSv1.3;
    server_tokens off;
    client_max_body_size 64k;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy no-referrer always;
    location / {{
        proxy_pass http://127.0.0.1:9080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_read_timeout 65s;
    }}
}}
'''

def issue(agent,host,email):
    host=hostname(host)
    if not isinstance(email,str) or len(email)>254 or not __import__('re').fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise ValueError('Valid SSL notification email required.')
    public=endpoint(agent.config['endpoint']);expected={x[4][0] for x in socket.getaddrinfo(public,None)};actual={x[4][0] for x in socket.getaddrinfo(host,None)}
    if not actual or not actual.issubset(expected): raise ValueError('All domain A/AAAA records must point to this VPS; remove stale records first.')
    paths=[Path('/etc/nginx/conf.d/vpn-panel.conf'),Path('/etc/ocserv/ocserv.conf'),Path('/etc/vpn-panel/xray.json')]
    old={p:p.read_text() for p in paths}
    # Route this hostname's HTTP-01 requests to our webroot before issuance.
    import re
    current_cert=re.search(r'ssl_certificate ([^;]+);',old[paths[0]]).group(1)
    current_key=re.search(r'ssl_certificate_key ([^;]+);',old[paths[0]]).group(1)
    try:
        atomic_write(paths[0],nginx_config(current_cert,current_key,host),0o644)
        run(['nginx','-t']);run(['systemctl','reload','nginx'])
        run(['certbot','certonly','--webroot','-w','/var/lib/vpn-panel/acme','-d',host,'--email',email,'--agree-tos','--non-interactive'],timeout=180)
    except Exception:
        atomic_write(paths[0],old[paths[0]],0o644);run(['systemctl','reload','nginx'],check=False);raise
    cert=f'/etc/letsencrypt/live/{host}/fullchain.pem';key=f'/etc/letsencrypt/live/{host}/privkey.pem'
    try:
        atomic_write(paths[0],nginx_config(cert,key,host),0o644)
        cfg=old[paths[1]]
        import re
        cfg=re.sub(r'^server-cert = .*$',f'server-cert = {cert}',cfg,flags=re.M);cfg=re.sub(r'^server-key = .*$',f'server-key = {key}',cfg,flags=re.M)
        atomic_write(paths[1],cfg)
        xray=json.loads(old[paths[2]]);xray['inbounds'][0]['streamSettings']={'network':'tcp','security':'tls','tlsSettings':{'certificates':[{'certificateFile':cert,'keyFile':key}]}}
        run(['nginx','-t']);run(['ocserv','-t','-c',str(paths[1])])
        agent.protocols.apply_xray(xray)
        run(['systemctl','reload','nginx']);run(['systemctl','restart','ocserv'],timeout=45)
        agent.state.set_setting('endpoint',host);agent.state.set_setting('domain',host);agent.state.set_setting('xray_tls',True)
    except Exception:
        for p,contents in old.items(): atomic_write(p,contents,0o644 if p==paths[0] else 0o600)
        for unit in ('nginx','ocserv','vpn-panel-xray'): run(['systemctl','restart',unit],timeout=45,check=False)
        raise
    return {'domain':host,'panel_url':f'https://{host}:9443','note':'OpenConnect sessions may reconnect. Export new domain/TLS profiles.'}
