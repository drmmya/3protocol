#!/usr/bin/env bash
set -euo pipefail
# Only chains owned by this project are edited. Existing SSH rules are untouched.
WAN=$(python3 -c 'import json; print(json.load(open("/etc/vpn-panel/config.json"))["interface"])')
[[ "$WAN" =~ ^[a-zA-Z0-9_.:-]+$ ]] || exit 1
start() {
  iptables -N VPNP_INPUT 2>/dev/null || true
  iptables -N VPNP_FORWARD 2>/dev/null || true
  iptables -t nat -N VPNP_NAT 2>/dev/null || true
  iptables -F VPNP_INPUT
  iptables -F VPNP_FORWARD
  iptables -t nat -F VPNP_NAT
  iptables -A VPNP_INPUT -p tcp -m multiport --dports 80,443,8443,4443,9443 -j ACCEPT
  iptables -A VPNP_INPUT -p udp -m multiport --dports 1194,8443,4443 -j ACCEPT
  for pool in 10.70.0.0/16 10.71.0.0/16 10.72.0.0/16; do
    iptables -A VPNP_FORWARD -s "$pool" -o "$WAN" -j ACCEPT
    iptables -A VPNP_FORWARD -d "$pool" -i "$WAN" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    iptables -t nat -A VPNP_NAT -s "$pool" -o "$WAN" -j MASQUERADE
  done
  iptables -C INPUT -j VPNP_INPUT 2>/dev/null || iptables -I INPUT 1 -j VPNP_INPUT
  iptables -C FORWARD -j VPNP_FORWARD 2>/dev/null || iptables -I FORWARD 1 -j VPNP_FORWARD
  iptables -t nat -C POSTROUTING -j VPNP_NAT 2>/dev/null || iptables -t nat -I POSTROUTING 1 -j VPNP_NAT
}
stop() {
  iptables -D INPUT -j VPNP_INPUT 2>/dev/null || true
  iptables -D FORWARD -j VPNP_FORWARD 2>/dev/null || true
  iptables -t nat -D POSTROUTING -j VPNP_NAT 2>/dev/null || true
  for chain in VPNP_INPUT VPNP_FORWARD; do
    iptables -F "$chain" 2>/dev/null || true
    iptables -X "$chain" 2>/dev/null || true
  done
  iptables -t nat -F VPNP_NAT 2>/dev/null || true
  iptables -t nat -X VPNP_NAT 2>/dev/null || true
}
case "${1:-start}" in start) start;; stop) stop;; *) exit 1;; esac
