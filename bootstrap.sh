#!/usr/bin/env bash
# Host this file with the full repository. Download it, then run with --repo.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run as root.'; exit 1; }
[[ "${1:-}" == --repo && "${2:-}" =~ ^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(\.git)?$ ]] || { echo 'Usage: bash bootstrap.sh --repo https://github.com/OWNER/REPO [main]'; exit 1; }
REPO=${2%.git};BRANCH=${3:-main}
[[ "$BRANCH" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo 'Invalid branch.'; exit 1; }
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 && -d /run/systemd/system && -c /dev/net/tun ]] || { echo 'Ubuntu 24.04 systemd VPS with TUN required.'; exit 1; }
command -v curl >/dev/null || { apt-get update; apt-get install -y curl ca-certificates; }
command -v python3 >/dev/null || apt-get install -y python3
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fL --connect-timeout 15 --max-time 120 "$REPO/archive/refs/heads/$BRANCH.zip" -o "$TMP/source.zip"
python3 - "$TMP" <<'PY'
import sys,zipfile
from pathlib import Path
root=Path(sys.argv[1])
with zipfile.ZipFile(root/'source.zip') as z:
    if sum(x.file_size for x in z.infolist())>100*1024*1024:raise SystemExit('Source archive too large.')
    for x in z.infolist():
        resolved=(root/x.filename).resolve()
        if root.resolve() not in resolved.parents:raise SystemExit('Unsafe archive path.')
    z.extractall(root)
PY
mapfile -t SCRIPTS < <(find "$TMP" -mindepth 2 -maxdepth 2 -name install.sh -type f)
[[ ${#SCRIPTS[@]} == 1 ]] || { echo 'Repository must contain one top-level install.sh.'; exit 1; }
bash "${SCRIPTS[0]}"
