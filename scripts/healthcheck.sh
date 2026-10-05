#!/usr/bin/env bash
set -euo pipefail
export XRAY_LOCATION_ASSET=/usr/local/share/xray
for unit in vpn-panel-agent vpn-panel-web vpn-panel-xray vpn-panel-firewall openvpn-server@panel-udp openvpn-server@panel-tcp ocserv nginx; do
  systemctl is-active --quiet "$unit" || { echo "Unhealthy service: $unit"; journalctl -u "$unit" -n 15 --no-pager; exit 1; }
done
[[ $(sysctl -n net.ipv4.ip_forward) == 1 ]] || exit 1
for port in 443 8443 4443 9443 9080 10085; do ss -H -lnt "sport = :$port" | grep -q . || { echo "Missing TCP listener $port"; exit 1; }; done
for port in 1194 8443 4443; do ss -H -lnu "sport = :$port" | grep -q . || { echo "Missing UDP listener $port"; exit 1; }; done
curl -ksSf --max-time 10 https://127.0.0.1:9443/ >/dev/null
nginx -t
ocserv -t -c /etc/ocserv/ocserv.conf
/usr/local/bin/xray run -test -config /etc/vpn-panel/xray.json
printf 'All local services, listeners, forwarding and HTTPS checks passed.\n'
