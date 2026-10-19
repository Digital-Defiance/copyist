#!/usr/bin/env bash
# Build the Mac .app / .dmg with Tauri, after the engine (and optional sidecars) are staged.
#
# Usage:
#   scripts/package/bundle-mac.sh              # unsigned (local smoke test)
#   scripts/package/bundle-mac.sh --sign       # Developer ID + notarize
#
# For --sign, either export the env vars below or let this script pick the
# Digital Defiance Developer ID from the keychain (Jessica has one).
#
#   APPLE_SIGNING_IDENTITY   e.g. "Developer ID Application: Digital Defiance (J6887N729S)"
#   APPLE_ID                 Apple ID email for notarization
#   APPLE_PASSWORD           app-specific password (appleid.apple.com → App-Specific Passwords)
#   APPLE_TEAM_ID            e.g. J6887N729S
#
# Or App Store Connect API key instead of Apple ID password:
#   APPLE_API_ISSUER, APPLE_API_KEY, APPLE_API_KEY_PATH (path to AuthKey_XXX.p8)
#
# Needs: freeze-engine.sh already run for this Mac's triple; Node + Rust (app/README.md).
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
sign=0
[[ "${1:-}" == "--sign" ]] && sign=1

case "$(uname -m)" in
  arm64) triple=aarch64-apple-darwin ;;
  x86_64) triple=x86_64-apple-darwin ;;
  *) echo "Unsupported Mac arch" >&2; exit 1 ;;
esac

engine="$root/app/src-tauri/binaries/copyist-engine-$triple"
if [[ ! -x "$engine" ]] || head -1 "$engine" | grep -q '^#!/bin/sh'; then
  echo "Frozen engine missing or still the dev script. Run:" >&2
  echo "  scripts/package/freeze-engine.sh $triple" >&2
  exit 1
fi

bin_dir="$root/app/src-tauri/binaries"
# Optional Metal / sfizz sidecars from the developer cache (same folder as the engine in the .app).
for name in yue-synth yue-plan yue-transcribe yue-tokenize sfizz_render; do
  src=""
  [[ -x "$root/.cache/yue2.cpp/build/$name" ]] && src="$root/.cache/yue2.cpp/build/$name"
  [[ -x "$root/.cache/sfizz/$name" ]] && src="$root/.cache/sfizz/$name"
  if [[ -n "$src" ]]; then
    cp "$src" "$bin_dir/$name-$triple"
    chmod +x "$bin_dir/$name-$triple"
    echo "Staged $name"
  fi
done

# Tell Tauri about every staged sidecar (engine is always required).
python3 - <<PY
import json
from pathlib import Path
conf = Path("$root/app/src-tauri/tauri.conf.json")
data = json.loads(conf.read_text())
triple = "$triple"
bins = Path("$bin_dir")
external = ["binaries/copyist-engine"]
for name in ("yue-synth", "yue-plan", "yue-transcribe", "yue-tokenize", "sfizz_render"):
    if (bins / f"{name}-{triple}").is_file():
        external.append(f"binaries/{name}")
data.setdefault("bundle", {})["externalBin"] = external
conf.write_text(json.dumps(data, indent=2) + "\n")
print("externalBin:", external)
PY

pick_identity() {
  # Prefer Digital Defiance's Developer ID Application, then Jessica's.
  local line
  line="$(security find-identity -v -p codesigning 2>/dev/null \
    | grep 'Developer ID Application: Digital Defiance' | head -1 || true)"
  if [[ -z "$line" ]]; then
    line="$(security find-identity -v -p codesigning 2>/dev/null \
      | grep 'Developer ID Application:' | head -1 || true)"
  fi
  # "  7) HASH "Developer ID Application: Name (TEAM)""
  sed -n 's/.*"\(Developer ID Application: .*\)".*/\1/p' <<<"$line"
}

cd "$root/app"
if [[ ! -d node_modules ]]; then
  npm install
fi

if [[ "$sign" -eq 1 ]]; then
  if [[ -z "${APPLE_SIGNING_IDENTITY:-}" ]]; then
    APPLE_SIGNING_IDENTITY="$(pick_identity)"
    export APPLE_SIGNING_IDENTITY
  fi
  if [[ -z "${APPLE_SIGNING_IDENTITY:-}" ]]; then
    echo "No Developer ID Application identity in the keychain." >&2
    echo "Install a Developer ID cert from developer.apple.com, or set APPLE_SIGNING_IDENTITY." >&2
    exit 1
  fi
  echo "Signing as: $APPLE_SIGNING_IDENTITY"

  if [[ -z "${APPLE_TEAM_ID:-}" ]]; then
    # TEAMID from "… (J6887N729S)"
    APPLE_TEAM_ID="$(sed -n 's/.*(\([A-Z0-9]\{10\}\))$/\1/p' <<<"$APPLE_SIGNING_IDENTITY")"
    export APPLE_TEAM_ID
  fi

  if [[ -z "${APPLE_API_KEY:-}" && -z "${APPLE_ID:-}" ]]; then
    echo "Notarization needs either:" >&2
    echo "  APPLE_ID + APPLE_PASSWORD (app-specific) + APPLE_TEAM_ID=$APPLE_TEAM_ID" >&2
    echo "or APPLE_API_ISSUER + APPLE_API_KEY + APPLE_API_KEY_PATH" >&2
    exit 1
  fi
  if [[ -n "${APPLE_ID:-}" && -z "${APPLE_PASSWORD:-}" ]]; then
    echo "Set APPLE_PASSWORD to an app-specific password from appleid.apple.com" >&2
    exit 1
  fi

  export APPLE_SIGNING_IDENTITY APPLE_TEAM_ID
  [[ -n "${APPLE_ID:-}" ]] && export APPLE_ID APPLE_PASSWORD
  [[ -n "${APPLE_API_KEY:-}" ]] && export APPLE_API_ISSUER APPLE_API_KEY APPLE_API_KEY_PATH

  echo "Building signed + notarized (Tauri will submit to Apple; this can take several minutes)…"
  npm run build
else
  echo "Building unsigned (local smoke test). For distribution: scripts/package/bundle-mac.sh --sign"
  npm run build
fi

echo
echo "Artifacts:"
find "$root/app/src-tauri/target/release/bundle" -maxdepth 3 \( -name '*.app' -o -name '*.dmg' \) 2>/dev/null || true

if [[ "$sign" -eq 1 ]]; then
  dmg="$(find "$root/app/src-tauri/target/release/bundle/dmg" -name '*.dmg' 2>/dev/null | head -1 || true)"
  if [[ -n "$dmg" ]]; then
    echo
    echo "SHA-256 for Casks/copyist.rb:"
    shasum -a 256 "$dmg"
    echo
    echo "Smoke-check notarization: spctl -a -vv --type install \"$dmg\""
  fi
fi
