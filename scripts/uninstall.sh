#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run as root.'; exit 1; }
echo 'This stops all managed VPN sessions and removes panel services. User database and certificates stay in /var/lib/vpn-panel and /etc/vpn-panel.'
read -r -p 'Type REMOVE to uninstall: ' ANSWER
[[ "$ANSWER" == REMOVE ]] || exit 1
for unit in vpn-panel-web vpn-panel-agent vpn-panel-xray openvpn-server@panel-udp openvpn-server@panel-tcp ocserv vpn-panel-firewall; do
  systemctl disable --now "$unit" || true
done
rm -f /etc/systemd/system/vpn-panel-{web,agent,xray,firewall}.service
rm -rf /etc/systemd/system/openvpn-server@panel-udp.service.d /etc/systemd/system/openvpn-server@panel-tcp.service.d
rm -f /etc/nginx/conf.d/vpn-panel.conf /etc/letsencrypt/renewal-hooks/deploy/vpn-panel.sh
rm -f /etc/openvpn/server/panel-{udp,tcp}.conf
rm -f /etc/sysctl.d/90-vpn-panel.conf /etc/logrotate.d/vpn-panel
# Preserve ocserv credentials/configuration and installed OS packages.
systemctl daemon-reload
nginx -t && systemctl reload nginx
printf 'Services removed; data and certificates preserved. Forwarding sysctl is left as-is to protect unrelated services.\n'
