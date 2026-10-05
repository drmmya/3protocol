# Easin VPN Panel v2 — Ubuntu 24.04

A lightweight self-hosted web administration panel and source installer for OpenVPN Community, OpenConnect/ocserv and V2Ray-compatible Xray VMess TCP/mKCP endpoints. Native systemd services; Python standard library backend; no Node build or paid control-plane dependency.

**Release status:** source implementation with local tests. Not a production-certified release: an actual Ubuntu VPS routing/ACME test and compatibility testing against your Android app are still required. Read [verification and limitations](docs/VERIFICATION.md).

## Install from the ZIP

Use a fresh Ubuntu 24.04 amd64/arm64 VPS with working TUN, systemd, root/sudo, at least 1.5 GB free disk, and outbound access to Ubuntu repositories, GitHub releases and Let's Encrypt.

Upload `EasinVPN-Panel-v2.zip` to `/root`, extract it, and run:

```bash
sudo apt-get update && sudo apt-get install -y unzip
sudo unzip /root/EasinVPN-Panel-v2.zip -d /root
sudo bash /root/vpn-panel/install.sh
```

On first installation, the installer asks only for the panel password (8–256 characters). Username is fixed to `Admin`. There is no built-in password and no default account for any VPN protocol. Create VPN accounts in Users after logging in. Reinstallation preserves existing accounts and the Admin password.

Open `https://YOUR_VPS_IP:9443`. IP-only HTTPS is self-signed: compare the installer certificate fingerprint before trusting it.

To set a specific reachable IPv4 or DNS endpoint, export `VPN_ENDPOINT` before installation. Public IPv4 is detected automatically otherwise. Native IPv6-only VPS installation is not supported by this IPv4-first network configuration.

## GitHub hosting and one-command bootstrap

Upload this archive's `vpn-panel/` **contents** to a GitHub repository so `install.sh`, `bootstrap.sh`, `panel/`, and `scripts/` are at the repository root. Do not include private launchers, backups or server data.

For example, after uploading the source to `https://github.com/drmmya/test`, run as root in PuTTY:

```bash
sudo apt update && sudo apt install -y git curl python3 && git clone https://github.com/drmmya/test /root/vpn-panel-final && cd /root/vpn-panel-final && sudo bash install.sh
```

Use your actual repository URL. The destination must not already exist. To update the same checkout later:

```bash
cd /root/vpn-panel-final && git pull --ff-only && sudo bash install.sh
```

No private launcher is needed. Upload the **contents** of `vpn-panel/`, so `install.sh` is at the GitHub repository root.

## Ports

| Purpose | Port |
|---|---|
| OpenVPN | 1194/UDP and 443/TCP |
| OpenConnect | 8443/TCP TLS and 8443/UDP DTLS |
| Xray VMess | 4443/TCP and 4443/UDP mKCP |
| Web panel | 9443/TCP HTTPS |
| Optional domain certificate validation | 80/TCP |
| Private backend / Xray API | 127.0.0.1:9080 / 127.0.0.1:10085 |

Open these public ports in your VPS provider firewall. Do not expose 9080, 10085 or management sockets. A native VMess/mKCP listener uses UDP 4443; select its separate profile in Users → Config. The server enables the documented `mkcp-legacy` default XOR packet framing for compatibility with legacy no-header/no-seed mKCP clients; VMess provides content encryption. Modern Xray clients should use the complete JSON export, which includes the matching FinalMask. A `net=kcp` URI alone does not establish wire compatibility for every client. Validate the pinned core and your Android app before relying on UDP. mKCP can consume more bandwidth than TCP.

## Panel features

- Live CPU, RAM, disk bars, load, uptime and observed VPS network throughput.
- Persistent today's/lifetime VPN traffic and 30-day daily charts/CSV.
- OpenVPN/OpenConnect active sessions; Xray online-source observations where the engine API returns them.
- Add/edit/remove/enable/block users, password reset, protocol access, user quotas.
- OpenVPN active-session download shaping/upload policing and persisted per-session user speed policy.
- OpenConnect native per-session user speed limits; settings apply on reconnect.
- Copy/download `.ovpn`, OpenConnect endpoint details, TCP/UDP VMess links and complete UDP Xray client JSON.
- Service start/stop/restart, journal/access logs, connection/authentication audit and background operation results.
- Optional domain SSL issuance, automated renewal and domain/TLS profile export.
- No configured per-user concurrent-device cap. VPS/OS/address-pool capacity still bounds concurrent sessions.

Shared credentials are intentionally supported. Sessions and public source addresses are not exact physical devices. Block-user affects that user's sessions; session-disconnect does not permanently ban a physical device. Independent per-device identity needs unique credentials or Android app registration. Xray per-user/per-device speed shaping is not implemented and rejected rather than silently ignored.

New installations use OpenVPN pools 10.70.0.0/16 and 10.71.0.0/16; ocserv uses 10.72.0.0/16. Reruns preserve existing engine pool configuration. No per-account concurrent-device cap is configured. Finite address space, OS limits and available VPS resources still bound total capacity; do not interpret unlimited account access as infinite server capacity.

## Domain and free SSL

Create a DNS A record pointing your desired subdomain at the VPS. Remove wrong AAAA records; the panel requires every resolved address to match its configured VPS endpoint. Go to Domain & SSL, enter hostname and email, then Install free SSL. The panel configures an existing hostname; it does not create DNS records or buy/register a domain.

HTTP-01 validation uses TCP 80, because OpenVPN owns TCP 443. The panel stays on 9443 after adding the domain. Trusted certificates are applied to panel HTTPS, OpenConnect and VMess TLS. Re-export client profiles after endpoint/TLS changes. OpenConnect/Xray sessions may reconnect during issuance or renewal.

## Operations and diagnostics

```bash
sudo bash /opt/vpn-panel/scripts/healthcheck.sh
sudo journalctl -u vpn-panel-agent -u vpn-panel-web -n 100 --no-pager
sudo bash /opt/vpn-panel/scripts/backup.sh
sudo bash /opt/vpn-panel/scripts/uninstall.sh
```

Backups contain server keys and hashed credentials; keep them private. Backup uses SQLite's online backup operation, not an inconsistent copy of a live WAL database. Uninstall asks for `REMOVE`, disconnects sessions and removes managed service wiring; it preserves server data and installed packages. There is no panel restore UI. Restore from a root-only backup with services stopped and verify ownership before restarting.

Installation logs: `/var/log/vpn-panel-install.log`. Re-running installation preserves credentials and generated configuration. If initial installation fails after package setup, inspect logs before rerunning; partial-install state may require repair described below. A rerun refreshes code/binaries and validates/services, so it is an update operation that can reconnect sessions.

### Troubleshooting

- **Preflight rejects ports/config:** use a fresh VPS or resolve the specific conflict; installer will not remove another VPN configuration.
- **Connection works but no Internet:** run healthcheck; check provider firewall, IPv4 forwarding and `iptables -t nat -S VPNP_NAT`. Then test from a real client.
- **Panel unavailable:** allow 9443 externally and inspect `systemctl status vpn-panel-web nginx`; self-signed HTTPS is expected before a domain.
- **Data unavailable/degraded:** inspect the displayed adapter error and agent journal. No reported connections can indicate collector failure; don't infer a healthy empty server from a missing count.
- **ocserv traffic fields differ:** the adapter uses JSON RX/TX, then panel-owned per-session tunnel interface counters. Unknown formats/devices show a collection error.
- **Xray online count unavailable:** the adapter requests `statsonline --email=<user>`; an unsupported/missing counter stays unknown. Source counts do not prove device identity.
- **Cloudflare domain:** use DNS-only mode; normal proxied HTTP does not carry all these VPN listeners.
- **Initial failed setup:** inspect existing `/etc/vpn-panel/config.json`, engine files and logs. Do not delete working user data. Re-run the installer after fixing dependencies/ports. If a failure happened before managed config was created but ocserv was installed, its stock file may trip preflight; verify it is only an unused package default before moving it aside.
- **IPv6 privacy:** OpenVPN profiles/server route IPv6 into a blocking tunnel. OpenConnect is IPv4-only; your Android VPN app must block or safely route IPv6. Do not assume complete IPv6 leak protection without a client test.

## Development checks

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q panel scripts
node --check panel/static/app.js
node tests/test_ui_jobs.cjs
bash -n install.sh bootstrap.sh scripts/*.sh
```

`tests/ui_fixture.py` is a synthetic HTTPS fixture for testing the UI, not a VPN server. It is not started by the installer. Python tests need no external packages. Browser layout verification requires an available browser runtime. See `docs/design.md`, the implementation plan and `docs/VERIFICATION.md` for exact scope and evidence.
