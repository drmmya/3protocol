"""OpenVPN auth-user-pass-verify hook. Never logs credentials."""
import sys,os
from pathlib import Path
from .common import load_config
from .state import State

def main():
    try:
        credentials=Path(sys.argv[1]).read_text().splitlines()
        if len(credentials)!=2: return 1
        s=State(load_config()['state']);valid=s.verify(credentials[0],credentials[1])
        s.event('auth',credentials[0][:64]+(' accepted' if valid else ' rejected'))
        return 0 if valid else 1
    except Exception: return 1
if __name__=='__main__': sys.exit(main())
