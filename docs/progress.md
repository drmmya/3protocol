# Execution ledger — 2026-10-05-vpn-panel
User explicitly overrides staged confirmations; execute continuously inline.
Fresh standalone repository on feature/vpn-panel; no existing project or main branch to disturb.
Ruling: Python standard library HTTP server behind Nginx replaces FastAPI — no third-party runtime Python downloads required, lower installer dependency risk.
Preflight: normalized protocol sessions feed State.account; socket JSON supplies web snapshots and mutations. All input names pass common validators.
Task 1: complete — password, user validation, duplicate-session/reset accounting; 9 core tests green.
Task 2: complete locally — real adapter code, agent command boundary, shaping and domain jobs; protocol/agent tests green. Live engine verification unavailable.
Task 3: implementation complete; HTTP auth/CSRF/session tests green, installer safe preflight rejects this non-systemd container without making changes. Browser runtime currently lacks Chromium executable.
Ruling: Supports user block/quota for all engines, OpenVPN session shaping and ocserv native per-session rates; Xray per-device shaping remains unsupported because shared UUIDs do not provide an enforceable per-device identity.
Ruling: OpenConnect IPv4-only server requires client/app IPv6 blocking; universal full-tunnel privacy cannot be asserted without inspecting the app.

Final: independent review findings fixed with failing-then-passing regression tests; 47 Python tests plus UI outage contract green.
Ruling: Native UDP4443 added as VMess/mKCP with explicit legacy framing and complete modern-client JSON — fulfils the requested UDP listener while requiring real app/core interoperability validation.
Ruling: Use /16 rather than /24 pools — avoid a small initial total-session ceiling; actual VPS/OS/address capacity remains finite.
Task 4: final local verification complete; archive packaging next; keep local feature branch and deliver an archive as requested; no external publish/merge authorized or needed.

Final UDP review: missing-listener migration preserves TCP/TLS/user UUIDs; firewall restart reapplies UDP4443 on reruns; explicit mkcp-legacy framing and matching complete client JSON address the documented raw/legacy distinction. Real wire/core validation is still required.
Final: 47 Python tests and the UI job outage contract pass; shell, Python and JS syntax checks pass. Browser executable absent and live VPS/TUN/systemd tests unavailable. No deferred reviewer findings remain in source scope.

v2: password-only Admin installation, no protocol account seeding, GitHub root upload instructions. 48 Python tests and UI outage contract pass.
