"""Shared validation and secret handling. No shell interpolation anywhere."""
import base64, hashlib, hmac, ipaddress, json, os, re, subprocess, tempfile
from pathlib import Path
PROTOCOLS=('openvpn','openconnect','v2ray')

def username(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',value):
        raise ValueError('Name must contain 1–64 letters, numbers, dots, underscores or hyphens.')
    return value

def hostname(value):
    value=str(value).lower().rstrip('.')
    try: ipaddress.ip_address(value)
    except ValueError: pass
    else: raise ValueError('Use a domain name, not an IP address.')
    if len(value)>253 or '.' not in value or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',x) for x in value.split('.')):
        raise ValueError('Invalid hostname.')
    return value

def endpoint(value):
    try: return str(ipaddress.ip_address(value))
    except ValueError: return hostname(value)

def hash_password(password):
    if not isinstance(password,str) or not 8<=len(password)<=256 or '\n' in password or '\r' in password: raise ValueError('Password must be 8–256 characters.')
    salt=os.urandom(16); digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1)
    return 'scrypt$'+base64.b64encode(salt).decode()+'$'+base64.b64encode(digest).decode()

def verify_password(password,stored):
    try:
        kind,salt,digest=stored.split('$')
        if kind!='scrypt' or not isinstance(password,str) or len(password)>256: return False
        actual=hashlib.scrypt(password.encode(),salt=base64.b64decode(salt,validate=True),n=16384,r=8,p=1)
        return hmac.compare_digest(actual,base64.b64decode(digest,validate=True))
    except (ValueError,TypeError): return False

def run(args,input=None,timeout=15,check=True):
    result=subprocess.run(args,input=input,text=True,capture_output=True,timeout=timeout)
    if check and result.returncode: raise RuntimeError(f'{Path(args[0]).name} failed: {result.stderr[-1000:] or result.stdout[-1000:]}')
    return result.stdout

def atomic_write(path,text,mode=0o600):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.candidate-')
    try:
        with os.fdopen(fd,'w') as f:
            os.fchmod(f.fileno(),mode); f.write(text); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def load_config():
    return json.loads(Path(os.environ.get('VPN_PANEL_CONFIG','/etc/vpn-panel/config.json')).read_text())
