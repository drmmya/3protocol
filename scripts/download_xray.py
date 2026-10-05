#!/usr/bin/env python3
"""Pinned upstream release download, checksum verification before execution."""
import hashlib,json,platform,re,sys,urllib.request,zipfile
from pathlib import Path
VERSION='v26.6.27'
def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Easin-VPN-Installer/1.0'})
    with urllib.request.urlopen(req,timeout=90) as response:return response.read()
def main():
    arch={'x86_64':'64','aarch64':'arm64-v8a'}.get(platform.machine())
    if not arch:raise ValueError('Only amd64 and arm64 are supported.')
    name=f'Xray-linux-{arch}.zip';base=f'https://github.com/XTLS/Xray-core/releases/download/{VERSION}/'
    payload=fetch(base+name);digest=fetch(base+name+'.dgst').decode()
    # Upstream dgst places SHA256 either on the label line or the following line.
    section=re.search(r'(?:SHA2?-?256)[^\n]*\n?[^\n]*',digest,re.I)
    candidates=re.findall(r'\b[0-9a-fA-F]{64}\b',section.group(0) if section else digest)
    expected=hashlib.sha256(payload).hexdigest()
    if expected not in [v.lower() for v in candidates]:raise ValueError('Upstream SHA256 check failed. Nothing installed.')
    target=Path(sys.argv[1]);target.mkdir(parents=True,exist_ok=True);archive=target/name;archive.write_bytes(payload)
    with zipfile.ZipFile(archive) as z:
        for item in ('xray','geoip.dat','geosite.dat'):
            (target/item).write_bytes(z.read(item))
    (target/'SHA256.txt').write_text(expected+'  '+name+'\n')
    print(f'Verified Xray {VERSION}, SHA256 {expected}')
if __name__=='__main__':main()
