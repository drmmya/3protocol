# Verification report — source release

Independent code review completed; important findings were reproduced and fixed with regression tests. No external VPS or user Android app was supplied; actual VPN routing is unverified.

## Tests run locally

- Python standard-library unittest suite: 48 tests passed after review fixes and TCP/mKCP additions.
- Shell syntax: install/bootstrap/firewall/auth/backup/uninstall scripts passed bash parsing.
- Python compilation: panel and provision/downloader scripts passed.
- JavaScript parsing: app.js passed Node syntax check. A Node VM regression contract verifies operation failures remain visible even without a health sample.
- Installer `--check`: correctly rejected this non-systemd execution container before installation mutations. This is a safe rejection test, not an Ubuntu VPS install pass.
- Browser attempt: Playwright package exists but Chromium/headless-shell executable is absent. Visual browser checks could not run at that attempt; no screenshot is claimed as proof.

Tests cover password hashing, validation, blocked auth, durable accounting, duplicate-user sessions, counter reset/restart, timezone buckets, deleted-user restoration, adapter fixtures, private Xray API, port layout, firewall scoping, rejected arbitrary agent commands, job failures, live proc metrics, HTTP authentication, CSRF, secure cookie flags, brute-force limit, and password-change session invalidation.

## Must verify on a clean VPS

1. Actual apt dependency versions, Xray pinned release download/digest, certificate generation and daemon config validation.
2. Fresh install and successful rerun, file permissions, boot-time systemd startup, protocol listeners and local HTTPS.
3. Real OpenVPN UDP and TCP user login, shared user concurrency, Internet/DNS/IPv6 leak tests.
4. OpenConnect TLS/DTLS connection and throughput, user hash format, per-session counters, shared user concurrency and IPv6 app handling.
5. Xray VMess/TCP and native UDP mKCP interoperability, FinalMask/legacy framing compatibility against the pinned core and Android app, traffic stats, online-source API and TLS profile after domain change.
6. Quota/block persistence and reconnect behavior; OpenVPN tc download/upload limit and OpenConnect native rates measured from clients.
7. Public DNS/domain ACME issuance, failed issuance rollback, renewal and trust-chain checks.
8. Live desktop/mobile UI interactions, exports, interrupted SSE reconnect and stale/error presentation.

## Explicit limitations

- No exact physical-device count or durable per-device block for shared credentials.
- No Xray per-user/per-device rate enforcement. Native UDP mKCP is implemented in source but wire interoperability and pinned-core daemon validation remain unverified here.
- Sampled accounting can miss very short sessions/final bytes; not certified billing-grade accounting.
- Server logs are retained/rotated and panel output is bounded; use root journal/log files for the complete retained operational history.
- Finite /16 address pools and VPS/OS limits bound total routed concurrency; no per-account cap is configured.
- OpenConnect IPv6 leak handling requires the Android app; cannot be asserted from the server alone.
- Browser visual inspection and end-to-end server/client tests are required before a production claim.

## Independent review fixes

- Preserve the vendor OpenVPN config working directory.
- Retry failed quota-policy synchronization; cache applied state only after success.
- Differentiate reused ocserv IDs by connection start.
- Reject incomplete/malformed engine samples, preserve known session audit and shaping state on read failure.
- Reconcile OpenVPN speed rules after an engine epoch changes.
- Seed test accounts once and preserve intentional deletion on installer reruns.
- Read Xray logs through a bounded byte tail; validate before touching/restarting a running config.
- Keep operation results visible during collector outages.
- Migrate missing UDP listener without replacing TCP/TLS settings; reapply managed firewall on rerun.

The review confirms source behavior and tests, not real daemon, routed VPN, public SSL or browser visual correctness.

## v2 installation change
Admin username stays Admin; first install requests only its password. No VPN users are seeded. Existing users remain unchanged on upgrade. No private launcher is required.
