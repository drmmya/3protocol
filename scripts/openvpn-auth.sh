#!/bin/sh
cd /opt/vpn-panel || exit 1
exec /usr/bin/python3 -m panel.vpn_auth "$1"
