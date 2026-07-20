#!/usr/bin/env bash
# Install Docker (if needed) and start Weekmenu on the public IP via Caddy :80.
# Run as root: sudo bash scripts/setup_public_deploy.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this script with sudo:" >&2
  echo "  sudo bash scripts/setup_public_deploy.sh" >&2
  exit 1
fi

APP_USER="${SUDO_USER:-weekmenu}"

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
  chown "$APP_USER":"$APP_USER" data/recipes.sqlite3 || true
fi

echo "==> Starting Weekmenu (Caddy on :80 → app under /weekmenu)"
sg docker -c 'docker compose up -d --build' || docker compose up -d --build

echo
echo "Open http://<this-host-public-IP>/weekmenu"
echo "Open firewall port 80 only. Traffic is HTTP (plaintext) until you add a domain/HTTPS."
echo "Create accounts as an admin at /weekmenu/admin/users (login as Erick first)."
