#!/usr/bin/env bash
# Install Docker + Tailscale, start Weekmenu on localhost, and enable Tailscale Serve.
# Run as root: sudo bash scripts/setup_tailscale_serve.sh
#
# Optional: pass a Tailscale auth key to skip the browser login:
#   sudo TS_AUTHKEY=tskey-auth-... bash scripts/setup_tailscale_serve.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this script with sudo:" >&2
  echo "  sudo bash scripts/setup_tailscale_serve.sh" >&2
  exit 1
fi

APP_USER="${SUDO_USER:-weekmenu}"

echo "==> Installing Tailscale (if needed)"
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

echo "==> Installing Docker (if needed)"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

usermod -aG docker "$APP_USER" || true

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example and set SESSION_SECRET first." >&2
  exit 1
fi

mkdir -p data
if [[ ! -f data/recipes.sqlite3 ]]; then
  touch data/recipes.sqlite3
fi

echo "==> Building and starting Weekmenu (localhost:8000)"
# Use sudo docker so we do not depend on a re-login for the docker group.
docker compose up -d --build

echo "==> Bringing up Tailscale"
if [[ -n "${TS_AUTHKEY:-}" ]]; then
  tailscale up --auth-key="$TS_AUTHKEY" --hostname=weekmenu-vps
else
  # Non-interactive: print login URL and wait until the node is online.
  tailscale up --hostname=weekmenu-vps --timeout=10m || true
fi

# Wait until Tailscale reports an IP (user may still be completing browser login).
echo "Waiting for this machine to join your Tailnet..."
for _ in $(seq 1 120); do
  if tailscale ip -4 >/dev/null 2>&1; then
    break
  fi
  # Re-print status so the login URL stays visible if needed.
  tailscale status 2>/dev/null || true
  sleep 5
done

if ! tailscale ip -4 >/dev/null 2>&1; then
  echo "" >&2
  echo "Tailscale is not online yet. On this machine run:" >&2
  echo "  sudo tailscale up --hostname=weekmenu-vps" >&2
  echo "Open the URL it prints, log in, then re-run:" >&2
  echo "  sudo bash scripts/setup_tailscale_serve.sh" >&2
  exit 1
fi

echo "==> Enabling Tailscale Serve (HTTPS → http://127.0.0.1:8000)"
tailscale serve --bg --https=443 http://127.0.0.1:8000

echo ""
echo "Done."
echo "  Tailscale IPv4: $(tailscale ip -4)"
echo "  Serve status:"
tailscale serve status || true
echo ""
echo "From any device on your Tailnet, open the HTTPS URL shown above"
echo "(MagicDNS name like https://weekmenu-vps.<your-tailnet>.ts.net)."
echo "Public http://<VPS_IP>:8000 should remain closed."
