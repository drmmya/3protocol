#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
STAGE=preflight
FAIL_LOG=/var/log/vpn-panel-install.log
on_error() { local code=$?; printf '\nInstallation failed at stage: %s (exit %s). Read %s.\n' "$STAGE" "$code" "$FAIL_LOG" >&2; exit "$code"; }
trap on_error ERR
preflight() {
  [[ $EUID -eq 0 ]] || { echo 'Run as root: sudo bash install.sh'; return 1; }
  source /etc/os-release
  [[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || { echo 'Ubuntu 24.04 is required.'; return 1; }
  [[ -d /run/systemd/system ]] || { echo 'A real systemd VPS is required; unsupported container.'; return 1; }
  [[ -c /dev/net/tun ]] || { echo 'TUN is unavailable. Ask your VPS provider to enable TUN.'; return 1; }
  case $(uname -m) in x86_64|aarch64) ;; *) echo 'Only amd64/arm64 supported.'; return 1;; esac
  [[ $(df -Pk / | awk 'NR==2 {print $4}') -gt 1500000 ]] || { echo 'At least 1.5 GB free disk space required.'; return 1; }
  if [[ ! -f /etc/vpn-panel/config.json ]]; then
    for port in 443 8443 4443 9443 9080 10085; do
      if ss -H -lnt "sport = :$port" | read -r _; then echo "TCP $port already in use; use a fresh VPS or resolve the conflict."; return 1; fi
    done
    for port in 1194 8443 4443; do
      if ss -H -lnu "sport = :$port" | read -r _; then echo "UDP $port already in use."; return 1; fi
    done
    [[ ! -f /etc/ocserv/ocserv.conf ]] || { echo 'Existing ocserv configuration detected. Use a fresh VPS; it will not be overwritten.'; return 1; }
    [[ ! -f /usr/local/bin/xray ]] || { echo 'Existing Xray binary detected. Use a fresh VPS.'; return 1; }
    command -v python3 >/dev/null || { echo 'Python3 required for safe preflight; install it first.'; return 1; }
    python3 - "$ROOT" <<'PYROUTES'
import json,subprocess,sys
sys.path.insert(0,sys.argv[1])
from scripts.provision import network_conflicts
routes=json.loads(subprocess.check_output(['ip','-j','-4','route']))
conflicts=network_conflicts(routes)
if conflicts:raise SystemExit('VPN address-pool conflicts: '+', '.join(conflicts))
PYROUTES
  fi
  echo 'Preflight passed.'
}
preflight
if [[ "${1:-}" == --check ]]; then exit 0; fi
touch "$FAIL_LOG"
chmod 600 "$FAIL_LOG"
exec > >(tee -a "$FAIL_LOG") 2>&1
NEW=1
[[ ! -f /etc/vpn-panel/config.json ]] || NEW=0
if [[ $NEW -eq 1 ]]; then
  # Supplied privately, never echoed or saved as plaintext in this repository.
  if [[ -z "${PANEL_ADMIN_PASSWORD:-}" ]]; then read -r -s -p 'Set panel Admin password: ' PANEL_ADMIN_PASSWORD; printf '\n'; fi
  export PANEL_ADMIN_PASSWORD
  python3 - <<'PY'
import os
for key in ('PANEL_ADMIN_PASSWORD',):
    p=os.environ.get(key,'')
    if not 8<=len(p)<=256 or '\n' in p or '\r' in p:raise SystemExit('Passwords must be 8–256 characters, with no newlines.')
PY
fi
STAGE=dependencies
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends python3 nginx openvpn ocserv openssl certbot curl unzip iptables iproute2 ca-certificates logrotate qrencode
STAGE=endpoint
WAN=$(ip -4 route show default | awk 'NR==1 {print $5}')
[[ "$WAN" =~ ^[a-zA-Z0-9_.:-]+$ ]] || { echo 'Cannot detect default network interface.'; exit 1; }
if [[ $NEW -eq 1 ]]; then
  ENDPOINT=${VPN_ENDPOINT:-$(curl -4fsS --connect-timeout 10 --max-time 20 https://api.ipify.org)}
else
  ENDPOINT=$(python3 -c 'import json; print(json.load(open("/etc/vpn-panel/config.json"))["endpoint"])')
fi
STAGE=xray-download
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
python3 "$ROOT/scripts/download_xray.py" "$TMP"
install -m 755 "$TMP/xray" /usr/local/bin/xray
install -d -m 755 /usr/local/share/xray
install -m 644 "$TMP/geoip.dat" "$TMP/geosite.dat" /usr/local/share/xray/
export XRAY_LOCATION_ASSET=/usr/local/share/xray
STAGE=files
getent group vpn-panel >/dev/null || groupadd --system vpn-panel
id vpn-panel >/dev/null 2>&1 || useradd --system --gid vpn-panel --home-dir /var/lib/vpn-panel-web --shell /usr/sbin/nologin vpn-panel
install -d -m 755 /opt/vpn-panel
if [[ "$ROOT" != /opt/vpn-panel ]]; then
  cp -a "$ROOT/panel" "$ROOT/scripts" /opt/vpn-panel/
fi
find /opt/vpn-panel -type d -name __pycache__ -prune -exec rm -rf {} +
find /opt/vpn-panel -type d -exec chmod 755 {} +
find /opt/vpn-panel -type f -exec chmod 644 {} +
chmod 755 /opt/vpn-panel/scripts/*.sh
chown -R root:root /opt/vpn-panel
# On a fresh install only, ocserv.conf below is the package default, not existing user data.
if [[ $NEW -eq 1 ]]; then
  systemctl stop ocserv
  cp /etc/ocserv/ocserv.conf /etc/ocserv/ocserv.conf.package-backup
  rm /etc/ocserv/ocserv.conf
fi
STAGE=provision
cd /opt/vpn-panel
python3 scripts/provision.py --endpoint "$ENDPOINT" --interface "$WAN"
unset PANEL_ADMIN_PASSWORD
chown root:vpn-panel /etc/vpn-panel /etc/vpn-panel/config.json
chmod 750 /etc/vpn-panel
chmod 640 /etc/vpn-panel/config.json
chown -R vpn-panel:vpn-panel /var/lib/vpn-panel-web
chmod 711 /var/lib/vpn-panel
chmod 700 /var/lib/vpn-panel-web
chmod 755 /var/lib/vpn-panel/acme
chmod 750 /var/log/vpn-panel
STAGE=validation
nginx -t
ocserv -t -c /etc/ocserv/ocserv.conf
/usr/local/bin/xray run -test -config /etc/vpn-panel/xray.json
sysctl -p /etc/sysctl.d/90-vpn-panel.conf
STAGE=services
systemctl daemon-reload
systemctl stop vpn-panel-agent 2>/dev/null || true
systemctl enable --now vpn-panel-firewall vpn-panel-xray
systemctl restart vpn-panel-firewall
# Root-only user sync; no credentials are passed in command arguments.
python3 - <<'PY'
from panel.common import load_config
from panel.state import State
from panel.protocols import Protocols
cfg=load_config();Protocols(State(cfg['state']),cfg).sync_users()
PY
systemctl enable --now vpn-panel-agent
systemctl enable --now openvpn-server@panel-udp openvpn-server@panel-tcp ocserv vpn-panel-web nginx
systemctl restart openvpn-server@panel-udp openvpn-server@panel-tcp ocserv vpn-panel-web
systemctl reload nginx
systemctl enable --now certbot.timer
STAGE=healthcheck
bash scripts/healthcheck.sh
printf '\nPanel: https://%s:9443\nAdmin username: Admin\nVPN accounts: none created; add users from the panel.\n' "$ENDPOINT"
echo 'IP-only certificate fingerprint (compare before trusting):'
openssl x509 -in /etc/vpn-panel/pki/panel.crt -noout -fingerprint -sha256
echo 'Allow provider firewall: TCP 80,443,8443,4443,9443 and UDP 1194,8443,4443. SSH stays on its existing port.'
echo 'Local installation checks passed. Test actual VPN routing from your Android app before production use.'
