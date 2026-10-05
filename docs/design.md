# Three-protocol VPN panel — Ubuntu 24.04

Source implementation design • 5 October 2026 • Real VPS/client verification outstanding

## Outcome

A self-hosted, single-VPS VPN administration panel with OpenVPN, OpenConnect (ocserv), and a V2Ray-compatible Xray engine. Deliver a GitHub-ready source ZIP, an installer, uninstall/repair instructions, a test report and an operator guide. The user installs through PuTTY on Ubuntu 24.04. This is an actual VPN server administration system, not a dashboard containing simulated data.

## Deployment and ports

Use native systemd services rather than privileged containers. Support Ubuntu 24.04 on amd64 and arm64 where upstream artifacts are available. Installation detects the platform, public endpoint, default route, port conflicts, disk space, TUN availability, and forwarding support before changes. Missing prerequisites produce actionable errors. No existing service, firewall or configuration is silently removed.

| Service | Listener |
|---|---|
| OpenVPN UDP | 1194/UDP |
| OpenVPN TCP | 443/TCP |
| OpenConnect TLS and DTLS | 8443/TCP and 8443/UDP |
| Xray client endpoints | VMess/TCP 4443 and VMess/mKCP UDP 4443 |
| Admin panel | 9443/TCP HTTPS |
| ACME validation | 80/TCP when issuing/renewing domain certificates |
| Backend and management interfaces | Loopback or Unix socket only |

The selected transport design provides VMess/TCP plus a separate VMess/mKCP listener on UDP 4443. TCP can also carry application UDP traffic. The mKCP server explicitly selects the upstream `mkcp-legacy` default no-header/no-seed framing through FinalMask; complete client JSON includes the same settings. Legacy links are available but cannot express modern FinalMask by themselves. The pinned core must validate these configurations during installation and the Android app must be tested for wire compatibility. Domain/TLS applies to the TCP endpoint; mKCP content uses VMess encryption and has no outer TLS.

## Components

1. A responsive web UI with sidebar navigation, soft neutral surfaces, clear status badges, compact CPU/RAM/SSD bars, and charts inspired by the information layout of OpenVPN Access Server without copying its assets.
2. A Python API running under a dedicated unprivileged account, with SQLite in WAL mode for users, settings, traffic buckets, audit records and jobs.
3. A narrowly scoped root agent reachable only over a permission-controlled Unix socket. It supports a fixed command schema for service actions, configuration validation, certificate operations, session termination and shaping. It never accepts arbitrary shell commands or user-supplied paths.
4. Protocol adapters for two OpenVPN instances, ocserv, and Xray. Each adapter reports its actual health, configuration, sessions and counters independently.
5. A background collector that writes durable accounting and streams snapshots to the UI through server-sent events, plus a job worker for long operations.
6. Nginx for HTTPS and certificate renewal integration. VPN engines run independently of the web UI.

## Installation and credentials

The installer runs as root, checks prerequisites, installs pinned/tested dependencies, provisions PKI, creates services and users, applies scoped NAT/firewall rules, and verifies local listeners and health endpoints. Download failures stop the affected stage with a readable log. Re-running preserves users, certificates, counters and settings. It does not reset credentials on upgrades.

Create panel administrator `Admin` and OpenVPN/OpenConnect test user `Easin`. Use the password explicitly supplied by the user through private install-time environment/config input; do not commit that password to GitHub or include it in public logs. A documented one-command install accepts these variables. Passwords are hashed; root-only files hold unavoidable protocol secrets and certificate keys. Passwords are changeable from the panel. Xray gets a generated UUID and an exportable initial test profile.

OpenVPN has no configured concurrent-device restriction and permits the intended shared-login use across both listeners. Ocserv has no configured total or per-user client cap. Xray has no configured device cap. Resource exhaustion and OS limits still bound capacity. Separate, non-overlapping VPN address pools are used for OpenVPN UDP, OpenVPN TCP and ocserv. VPN IPv4 forwarding and DNS routing are configured; client IPv6 is explicitly handled to avoid claiming full-tunnel privacy while silently leaking IPv6. IPv6 tunnelling is enabled only with suitable VPS routing, otherwise the supported client profile blocks IPv6 outside the tunnel where possible and documents client requirements.

## Screens and live updates

- Dashboard: CPU %, RAM used/total, SSD used/total, system load, uptime, current ingress/egress rate, today's traffic, lifetime traffic, and connections per protocol.
- Users: add/edit/delete, enable/disable, password reset, protocol access, quota, bandwidth policy and configuration exports.
- Connections: authenticated user, protocol/listener, virtual IP, public source address where available, start time, received/sent bytes and current rate; disconnect action with explicit scope.
- Protocols: status, configuration summary, start/stop/restart, validation results and live operational logs.
- Reports: traffic history, authentication and connection events, administrator audit trail; filtered CSV export and downloadable diagnostics.
- Domains/HTTPS: hostname, DNS readiness, certificate state/expiry, issuance/renewal job progress and failure explanation.
- Settings: admin password, endpoint, timezone (initially Asia/Dhaka), retention, backup/export and resource thresholds.

Collectors sample at roughly two-second intervals; UI updates without whole-page refresh. Slow/offline protocol adapters show unavailable/stale data with timestamps, never a fake zero or fake connected state. Reconnects resume live updates. Mobile layout keeps critical health and control information visible.

## Counting and accounting

OpenVPN obtains session state and counters through its local management interface; ocserv through occtl and supported accounting/session hooks; Xray through its local statistics API and access events. Counter collection is adapter-version tested.

OpenVPN and ocserv show active VPN sessions, which are not automatically unique physical devices. Xray distinguishes configured users, online user/source observations, and transport connections. TCP sockets or shared public IP addresses are not labelled as exact physical devices. Exact device identity requires a separate profile/credential for each device or registration from the Android app. Shared credentials remain supported as requested.

Persist counter deltas with protocol-instance epochs to handle service restarts and counter resets without negative usage or double counting. Persist final session samples/hooks where supported. Daily buckets use the configured timezone; lifetime totals survive restarts. Sampling gaps and sources with incomplete close events are marked so the report does not promise exact billing-grade usage. VPS interface traffic includes management and protocol overhead; VPN user traffic is a separate metric and is not summed twice. Network speed means observed throughput, not a scheduled external speed test.

## Blocking, quota and speed policies

Block a user by disabling authentication and terminating known current sessions; ensure the restriction persists after reconnect and restart. Daily/lifetime quotas are enforceable against durable user counters with the documented sampling delay.

OpenVPN session shaping uses Linux tc keyed to assigned tunnel addresses and lifecycle hooks. Ocserv uses supported per-user rate directives; individual active-session shaping may also use the associated tunnel interface/address. Reconnect applies saved policies again. Duplicate shared-user sessions do not overwrite one another's session rules. Policies distinguish per-session limits from aggregate user limits.

For Xray, a unique user UUID enables user attribution and blocking. Shared config/source address does not establish a physical device identity. Exact independent per-device shaping requires device-specific profiles and an enforceable egress design. The initial implementation must either implement and test a dedicated shaping path for that scope or mark that control unsupported; it must not show a working-looking speed control that cannot enforce the selected policy. Total protocol/VPS bandwidth controls can be offered separately with accurate labels. This is a disclosed limitation of the initial design relative to the requested universal per-device controls.

## HTTPS and optional domains

IP-only panel setup starts with a private self-signed certificate and displays its fingerprint in installation output; browsers show a trust warning. Domain setup checks syntax and public DNS before requesting a trusted certificate. HTTP-01 uses port 80 because OpenVPN owns port 443. DNS is configured at the user's DNS provider; typing a hostname in the panel does not create DNS records. The panel supports assigning a pointed hostname and issuing/renewing its certificate, with an optional DNS integration only if explicitly added later.

Certificates renew automatically. Successful renewal reloads HTTPS configuration and applicable VPN certificates using the least disruptive supported operation. A failed issuance leaves the last working certificate and configuration intact. Domain/TLS changes affecting VPN client profiles are explained and new profiles can be exported.

## Safety, reliability and operations

Use secure HttpOnly/SameSite cookies, session expiry, CSRF protection for mutations, login throttling, parameter validation, hashed passwords, and audit logging. Do not expose management APIs publicly. No plaintext password logging or exported private server keys. Log rotation and configurable retention keep disk usage bounded.

Before applying a configuration change: back up managed configuration, validate candidate files, atomically replace, perform the action and check health. Failed changes roll back to the last working version where safe. Operations use locks to avoid concurrent conflicting writes. Service restarts disclose that active connections may disconnect. Installer manages only its own firewall chain/table and units and preserves SSH reachability. Uninstall has a separate explicit destructive confirmation and can preserve data backups.

## Verification and delivery criteria

Automated checks cover authentication/authorization, input validation, counters across resets/restarts, timezone day boundaries, quotas, configuration validation/rollback, collector failures and supported policy persistence. UI checks cover desktop/mobile layout, live updates, error states and exports. Installer syntax and non-destructive preflight are tested separately.

A clean Ubuntu 24.04 integration environment must verify installation and idempotent rerun, firewall/NAT/forwarding, listener ownership, real client authentication and routed traffic for both OpenVPN listeners, OpenConnect TCP and DTLS, and the selected Xray transport including UDP payloads. Verify concurrent shared-user connections, user edits/removal, reconnect and block persistence, supported shaping with measured throughput, service actions, accounting durability, certificate issuance/renewal and recovery. An external reachable VPS/domain is required for public ACME and real external-client tests.

If the current execution environment cannot run a real VPS/network integration test, the final report explicitly lists what passed locally and what remains unverified. A successful source build or attractive UI is not reported as proof that VPN routing works.

## Delivery boundaries

Deliver a GitHub-ready archive with source, install script, locked versions/checksums, service templates, test suite, English operator guide, short Bangla installation guide, troubleshooting/repair and verification report. No publication to GitHub or installation on the user's VPS occurs without repository/server access. No billing, reseller hierarchy or external-device telemetry integration is included in this initial scope.

## Execution decision

The user explicitly instructed continuous implementation without further confirmation gates. VMess TCP/mKCP interoperability needs an actual app test; session/source counts remain distinct from physical-device identity. The Xray per-device shaping limitation remains explicit in the source release.
