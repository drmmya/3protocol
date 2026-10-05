#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || exit 1
umask 077
DEST=${1:-/root/vpn-panel-backup-$(date +%Y%m%d-%H%M%S).tar.gz}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
python3 - "$TMP" <<'PY'
import sqlite3,sys
from pathlib import Path
for src,name in [('/var/lib/vpn-panel/state.db','state.db'),('/var/lib/vpn-panel-web/admin.db','admin.db')]:
    with sqlite3.connect(src) as source,sqlite3.connect(Path(sys.argv[1])/name) as target:source.backup(target)
PY
tar -czf "$DEST" /etc/vpn-panel /etc/ocserv/panel.passwd /etc/ocserv/panel-users /etc/ocserv/ocserv.conf /etc/openvpn/server/panel-udp.conf /etc/openvpn/server/panel-tcp.conf -C "$TMP" state.db admin.db
chmod 600 "$DEST"
echo "Private backup created: $DEST (contains keys and password hashes)."
