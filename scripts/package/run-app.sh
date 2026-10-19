#!/usr/bin/env bash
# Run the desktop app in development against this checkout (easy path while packaging lands).
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root/app"

if ! command -v rustc >/dev/null; then
  echo "Rust is needed once: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh" >&2
  exit 1
fi
if [[ ! -x "$root/.venv/bin/python" ]]; then
  echo "Create the project venv first: python -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 1
fi
if [[ ! -d node_modules ]]; then
  npm install
fi
echo "Opening Copyist (Tauri). The engine uses $root"
exec npm run dev
